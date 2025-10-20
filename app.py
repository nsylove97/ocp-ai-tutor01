# app.py

# --- 1. Standard & 3rd Party Libraries ---
import streamlit as st
import streamlit_authenticator as stauth
import bcrypt
import random
import json
import os
from dotenv import load_dotenv
from streamlit_quill import st_quill
from streamlit_modal import Modal

# --- 2. Custom Modules ---
from gemini_handler import (
    generate_explanation, generate_modified_question, analyze_difficulty, get_chat_response, generate_session_title
)
# db_utils는 함수 단위로 명시적으로 임포트하여 가독성 및 안정성 향상
from db_utils import (
    setup_database_tables, load_original_questions_from_json, get_db_connection,
    get_all_question_ids, get_question_by_id, add_new_original_question, update_original_question,
    get_wrong_answers, delete_wrong_answer, get_all_modified_questions, save_modified_question,
    delete_modified_question, clear_all_modified_questions, get_stats, get_top_5_missed,
    fetch_all_users, add_new_user, delete_user, get_all_users_for_admin, ensure_master_account,
    get_question_ids_by_difficulty, clear_all_original_questions, export_questions_to_json_format,
    save_ai_explanation, get_ai_explanation_from_db, delete_ai_explanation,
    get_all_explanations_for_admin, get_chat_history, save_chat_message,
    get_chat_sessions, delete_chat_session,
    update_chat_session_title, get_full_chat_history, update_chat_message, delete_chat_message_and_following,
    delete_single_chat_message, delete_chat_messages_from, delete_single_original_question
)
from ui_components import display_question, display_results

# --- Constants ---
load_dotenv()
MEDIA_DIR = "media"
if not os.path.exists(MEDIA_DIR):
    os.makedirs(MEDIA_DIR)
MASTER_ACCOUNT_USERNAME = "admin"
MASTER_ACCOUNT_NAME = "Master Admin"
MASTER_ACCOUNT_PASSWORD = os.environ.get("MASTER_PASSWORD")

# 만약 .env 파일에 MASTER_PASSWORD가 설정되지 않았을 경우를 대비한 방어 코드
if not MASTER_ACCOUNT_PASSWORD:
    st.error("치명적인 오류: 마스터 계정의 비밀번호가 환경 변수에 설정되지 않았습니다. (.env 파일을 확인하세요)")
    st.stop() # 앱 실행을 중지

# --- Helper Functions ---
def get_ai_explanation(q_id, q_type):
    """
    AI 해설을 가져옵니다. DB에 저장된 해설이 있으면 그것을 반환하고,
    없으면 새로 생성하여 DB에 저장한 후 반환합니다.
    """
    # 1. DB에서 먼저 찾아보기
    explanation = get_ai_explanation_from_db(q_id, q_type)
    if explanation:
        st.toast("저장된 해설을 불러왔습니다.", icon="💾")
        return explanation

    # 2. DB에 없으면 새로 생성
    st.toast("AI가 새로운 해설을 생성합니다...", icon="🤖")
    question_data = get_question_by_id(q_id, q_type)
    if not question_data:
        return {"error": f"DB에서 문제(ID: {q_id}, Type: {q_type})를 찾을 수 없습니다."}
    
    new_explanation = generate_explanation(question_data)
    
    # 3. 생성된 해설을 DB에 저장 (오류가 아닌 경우에만)
    if "error" not in new_explanation:
        save_ai_explanation(q_id, q_type, json.dumps(new_explanation))
        
    return new_explanation

def initialize_session_state():
    defaults = {
        'current_view': 'home', 'questions_to_solve': [], 'current_question_index': 0,
        'user_answers': {}, 'current_edit_id': 1, 'new_option_count': 5,
        'temp_new_question': "", 'temp_new_options': {}
    }
    for key, value in defaults.items():
        if key not in st.session_state: st.session_state[key] = value

def start_quiz_session(quiz_mode, quiz_type=None, num_questions=None, question_id=None, difficulty=None):
    st.session_state.questions_to_solve = []
    st.session_state.user_answers = {}
    st.session_state.current_question_index = 0
    questions_loaded = False
    if quiz_mode == "랜덤 퀴즈":
        if quiz_type == '기존 문제':
            all_ids = get_question_ids_by_difficulty(difficulty)
            if all_ids:
                selected_ids = random.sample(all_ids, min(num_questions, len(all_ids)))
                st.session_state.questions_to_solve = [{'id': q_id, 'type': 'original'} for q_id in selected_ids]
                questions_loaded = True
            else: st.error("데이터베이스에 원본 문제가 없습니다.")
        elif quiz_type == '✨ AI 변형 문제':
            with st.spinner(f"{num_questions}개의 변형 문제를 생성 중입니다..."):
                original_ids = get_all_question_ids('original')
                if original_ids:
                    s_ids = random.sample(original_ids, min(num_questions, len(original_ids)))
                    new_ids = [save_modified_question(qid, gq) for qid in s_ids if (gq := generate_modified_question(get_question_by_id(qid))) and "error" not in gq]
                    if new_ids:
                        st.session_state.questions_to_solve = [{'id': q_id, 'type': 'modified'} for q_id in new_ids]
                        questions_loaded = True
                    else: st.error("AI 변형 문제 생성에 실패했습니다.")
                else: st.error("변형할 원본 문제가 없습니다.")
    elif quiz_mode == "ID로 문제 풀기":
        target_q = get_question_by_id(question_id, 'original')
        if target_q:
            st.session_state.questions_to_solve = [{'id': question_id, 'type': 'original'}]
            questions_loaded = True
        else: st.error(f"ID {question_id}에 해당하는 원본 문제를 찾을 수 없습니다.")
    if questions_loaded:
        st.session_state.current_view = 'quiz'
        st.rerun()

# --- UI Rendering Functions ---
def render_home_page():
    st.header("📝 퀴즈 설정")
    quiz_mode = st.radio("퀴즈 모드를 선택하세요:", ("랜덤 퀴즈", "ID로 문제 풀기"), horizontal=True)
    
    difficulty_options = ['쉬움', '보통', '어려움', '모든 난이도']

    if quiz_mode == "랜덤 퀴즈":
        col1, col2 = st.columns(2)
        with col1:
            num_questions = st.slider("문제 수:", 1, 50, 10, key="num_questions_slider")
        with col2:
            selected_difficulty = st.selectbox("난이도:", difficulty_options, index=3) # 기본값 '모든 난이도'

        quiz_type = st.radio("문제 유형:", ('기존 문제', '✨ AI 변형 문제'), key="quiz_type_selector")
        
        if st.button("랜덤 퀴즈 시작하기", type="primary"):
            # start_quiz_session 호출 시 difficulty 인자 전달
            start_quiz_session(quiz_mode, quiz_type=quiz_type, num_questions=num_questions, difficulty=selected_difficulty)
    else:
        q_id = st.number_input("문제 ID:", min_value=1, step=1)
        if q_id and (p_q := get_question_by_id(q_id, 'original')):
            with st.container(border=True):
                st.markdown(f"**미리보기 (ID: {p_q['id']})**"); st.markdown(p_q['question'], unsafe_allow_html=True)
        if st.button(f"ID {q_id} 풀기", type="primary"): start_quiz_session(quiz_mode, question_id=q_id)

def render_quiz_page():
    if not st.session_state.questions_to_solve:
        st.warning("풀 문제가 없습니다. 홈으로 돌아가 퀴즈를 다시 시작해주세요.")
        if st.button("홈으로"): st.rerun()
        return
    idx, total = st.session_state.current_question_index, len(st.session_state.questions_to_solve)
    st.progress((idx + 1) / total, text=f"{idx + 1}/{total} 문제 진행 중...")
    if idx not in st.session_state.user_answers: st.session_state.user_answers[idx] = []
    q_info = st.session_state.questions_to_solve[idx]
    if question := get_question_by_id(q_info['id'], q_info['type']):
        display_question(question, idx, total)
        c1, _, c2 = st.columns([1, 3, 1])
        if c1.button("이전", disabled=(idx == 0), use_container_width=True): st.session_state.current_question_index -= 1; st.rerun()
        if idx < total - 1:
            if c2.button("다음", use_container_width=True): st.session_state.current_question_index += 1; st.rerun()
        else:
            if c2.button("결과 보기", type="primary", use_container_width=True): st.session_state.current_view = 'results'; st.rerun()
    else: st.error(f"문제(ID: {q_info['id']})를 불러오는 데 실패했습니다.")

def render_notes_page(username):
    """'오답 노트' 화면을 렌더링합니다."""
    st.header("📒 오답 노트")
    wrong_answers = get_wrong_answers(username)

    if not wrong_answers:
        st.success("🎉 오답 노트가 비어있습니다.")
        return
    
    st.info(f"총 {len(wrong_answers)}개의 틀린 문제가 있습니다. 다시 풀어보거나 아래에서 상세 내용을 확인하세요.")
    if st.button("틀린 문제 다시 풀기", type="primary"):
        st.session_state.questions_to_solve = [{'id': q['question_id'], 'type': q['question_type']} for q in wrong_answers]
        st.session_state.current_question_index = 0
        st.session_state.user_answers = {}
        st.session_state.current_view = 'quiz'
        st.rerun()

    st.write("---")

    for row in wrong_answers:
        if not row:
            continue

        # sqlite3.Row 또는 dict 어떤 형태든 안전하게 dict로 변환
        try:
            question = dict(row)
        except Exception:
            question = row

        q_text = (question.get('question') or "") if isinstance(question, dict) else (question['question'] if 'question' in question else "")
        preview = q_text.replace('<p>', '').replace('</p>', '')[:50].strip() + "..." if q_text else "미리보기 없음"

        q_id = question.get('id') or question.get('question_id')
        q_type = question.get('question_type') or question.get('type') or 'original'

        with st.expander(f"**ID {q_id} ({q_type})** | {preview}"):
            # 질문 본문
            st.markdown("**질문:**")
            st.markdown(q_text, unsafe_allow_html=True)

            # 미디어 표시 (경로 존재 확인)
            media_url = question.get('media_url')
            media_type = question.get('media_type')
            if media_url and os.path.exists(media_url):
                if media_type == 'image':
                    st.image(media_url)
                else:
                    st.video(media_url)
            
            # 선택지 출력
            try:
                options = json.loads(question.get('options') or "{}")
                st.markdown("**선택지:**")
                for key, value in options.items():
                    st.write(f" - **{key}:** {value}")
            except (json.JSONDecodeError, TypeError):
                st.write("선택지를 불러올 수 없습니다.")
            
            # 정답 출력
            try:
                answer = json.loads(question.get('answer') or "[]")
                if isinstance(answer, list):
                    st.error(f"**정답:** {', '.join(answer)}")
                else:
                    st.error(f"**정답:** {answer}")
            except (json.JSONDecodeError, TypeError):
                st.error("정답 정보를 불러올 수 없습니다.")

            # AI 해설 버튼
            if st.button("🤖 AI 해설", key=f"note_exp_{q_id}_{q_type}"):
                with st.spinner("해설 생성 중..."):
                    if exp := get_ai_explanation(q_id, q_type):
                        if err := exp.get('error'):
                            st.error(err)
                        else:
                            st.info(f"**💡 쉬운 비유:**\n{exp.get('analogy', 'N/A')}")
                            st.info(f"**🔑 핵심 개념:**\n{exp.get('core_concepts', 'N/A')}")
def render_results_page(username):
    display_results(username, get_ai_explanation)
    if st.button("새 퀴즈 시작"): st.session_state.current_view = 'home'; st.rerun()

def render_management_page(username):
    """
    문제 추가/편집, 오답 노트, 사용자 관리 등 앱의 설정 및 데이터 관리 화면을 렌더링합니다.
    """
    st.header("⚙️ 설정 및 관리")
    is_admin = st.session_state.get('is_admin', False)

    # 탭 목록 정의
    common_tabs = ["원본 문제 데이터", "문제 추가", "문제 편집", "오답 노트 관리", "AI 변형 문제 관리", "AI 해설 관리"]
    tab_list = ["👑 사용자 관리"] + common_tabs if is_admin else ["👋 회원 탈퇴"] + common_tabs
    tabs = st.tabs(tab_list)
    
    # --- 조건부 탭 (첫 번째 탭) ---
    if is_admin:
        with tabs[0]: # 👑 사용자 관리 탭
            st.subheader("사용자 목록")
            all_users = get_all_users_for_admin()
            st.metric("총 등록된 사용자 수", f"{len(all_users)} 명")
            st.write("---")
            
            modal = Modal(title="⚠️ 삭제 확인", key="delete_user_modal")

            if 'user_to_delete' not in st.session_state:
                st.session_state.user_to_delete = None

            for user in all_users:
                if user['username'] != MASTER_ACCOUNT_USERNAME:
                    with st.container(border=True):
                        col1, col2 = st.columns([0.8, 0.2])
                        with col1:
                            st.markdown(f"**👤 {user['name']}** (`{user['username']}`)")
                        with col2:
                            # '계정 삭제' 버튼은 session_state를 변경하고 모달을 여는 역할
                            if st.button("계정 삭제", key=f"del_btn_{user['username']}", type="secondary", use_container_width=True):
                                st.session_state.user_to_delete = user['username']
                                modal.open() # ★★★★★ 상태 변경 후 즉시 모달 열기 ★★★★★
            
            # --- 2. 모달이 열려 있는지 확인하고 컨텐츠를 그림 ---
            if modal.is_open():
                with modal.container():
                    # 삭제할 대상이 session_state에 저장되어 있는지 다시 한번 확인
                    user_key = st.session_state.user_to_delete
                    if user_key:
                        st.warning(f"정말로 **{user_key}** 사용자를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.")
                        
                        c1, c2 = st.columns(2)
                        if c1.button("✅ 예, 삭제합니다", type="primary", use_container_width=True):
                            delete_user(user_key)
                            st.toast(f"사용자 '{user_key}'가 삭제되었습니다.", icon="🗑️")
                            st.session_state.user_to_delete = None # 상태 초기화
                            modal.close()
                            # st.rerun()은 modal.close()에 의해 자동으로 트리거될 수 있음
                        
                        if c2.button("❌ 아니요, 취소합니다", use_container_width=True):
                            st.session_state.user_to_delete = None # 상태 초기화
                            modal.close()
    else:
        with tabs[0]: #회원 탈퇴 탭
            st.subheader("회원 탈퇴")
            st.warning("회원 탈퇴 시 모든 학습 기록(오답 노트, 통계)이 영구적으로 삭제됩니다.")
            if st.checkbox("위 내용에 동의하며 탈퇴를 진행합니다.", key="delete_confirm"):
                if st.button("회원 탈퇴하기", type="primary"):
                    delete_user(username)
                    st.success("탈퇴 처리되었습니다. 이용해주셔서 감사합니다.")
                    st.session_state.clear()
                    st.session_state.authentication_status = None
                    st.rerun()

    # --- 공통 탭 (두 번째 탭부터) ---
    with tabs[1]: # 원본 문제 데이터
        st.subheader("📚 원본 문제 데이터 관리")
        
        # --- UI 레이아웃 구성 ---
        col1, col2 = st.columns(2)
        with col1: # 불러오기 및 초기화
            st.info("JSON 파일의 문제를 DB로 불러오거나, DB의 문제를 초기화합니다.")
            num_q = len(get_all_question_ids('original'))
            st.metric("현재 DB에 저장된 문제 수", f"{num_q} 개")
            
            analyze_option = st.checkbox("🤖 AI로 자동 난이도 분석 실행 (시간 소요)", value=False)
            
            if st.button("JSON에서 문제 불러오기", type="primary", use_container_width=True):
                try:
                    with open('questions_final.json', 'r', encoding='utf-8') as f:
                        questions_from_json = json.load(f)
                except FileNotFoundError:
                    st.error("`questions_final.json` 파일을 찾을 수 없습니다.")
                    st.stop()
                
                if not questions_from_json:
                    st.warning("JSON 파일에 문제가 없습니다.")
                else:
                    questions_to_load = []
                    if analyze_option:
                        progress_bar = st.progress(0, text="AI 난이도 분석 시작...")
                        total = len(questions_from_json)
                        for i, q in enumerate(questions_from_json):
                            q['difficulty'] = analyze_difficulty(q['question'])
                            questions_to_load.append(q)
                            progress_bar.progress((i + 1) / total, text=f"AI 분석 중... ({i+1}/{total})")
                        progress_bar.empty()
                        st.toast("AI 분석 완료! DB에 저장합니다.", icon="🤖")
                    else:
                        for q in questions_from_json:
                            q['difficulty'] = '보통'
                        questions_to_load = questions_from_json

                    count, error = load_original_questions_from_json(questions_to_load)
                    if error:
                        st.error(f"문제 저장 실패: {error}")
                    else:
                        st.success(f"모든 문제({count}개)를 성공적으로 불러왔습니다!")
                        st.rerun()

            with st.expander("⚠️ 문제 초기화 (주의)"):
                if st.button("모든 원본 문제 삭제", type="secondary", use_container_width=True):
                    clear_all_original_questions()
                    st.toast("모든 원본 문제가 삭제되었습니다.", icon="🗑️")
                    st.rerun()
        
        with col2: # 내보내기
            st.info("현재 DB 데이터를 JSON 파일로 저장(내보내기)합니다.")
            questions_to_export = export_questions_to_json_format()
            json_string = json.dumps(questions_to_export, indent=4, ensure_ascii=False)
            
            st.metric("내보낼 문제 수", f"{len(questions_to_export)} 개")
            
            st.download_button(
               label="📥 JSON 파일로 다운로드", data=json_string,
               file_name="questions_updated.json", mime="application/json"
            )
            
            st.warning("아래 버튼은 서버의 `questions_final.json` 파일을 직접 덮어씁니다.")
            if st.button("서버 파일에 덮어쓰기"):
                try:
                    with open("questions_final.json", "w", encoding="utf-8") as f:
                        f.write(json_string)
                    st.success("`questions_final.json` 파일이 업데이트되었습니다!")
                except Exception as e:
                    st.error(f"파일 쓰기 중 오류 발생: {e}")

        st.write("---")

# --- 공통 탭 (두 번째 탭부터) ---
    with tabs[2]: #문제 추가
        st.subheader("➕ 새로운 문제 추가")
        if 'temp_new_question' not in st.session_state: st.session_state.temp_new_question = ""
        st.session_state.temp_new_question = st_quill(value=st.session_state.temp_new_question, placeholder="질문 내용을 입력하세요...", html=True, key="quill_add")
        uploaded_file = st.file_uploader("미디어 첨부", type=['png', 'jpg', 'jpeg', 'mp4'], key="uploader_add")
        if 'new_option_count' not in st.session_state: st.session_state.new_option_count = 5
        st.number_input("선택지 개수:", min_value=2, max_value=10, key="new_option_count")
        if 'temp_new_options' not in st.session_state: st.session_state.temp_new_options = {}
        for i in range(st.session_state.new_option_count):
            letter = chr(ord('A') + i)
            st.session_state.temp_new_options[letter] = st.text_input(f"선택지 {letter}:", value=st.session_state.temp_new_options.get(letter, ""), key=f"temp_new_option_{letter}")
        with st.form(key="add_form_submit"):
            valid_options = [l for l, t in st.session_state.temp_new_options.items() if t.strip()]
            new_answer = st.multiselect("정답 선택:", options=valid_options)
            new_difficulty = st.selectbox("난이도 설정:", ('쉬움', '보통', '어려움'), index=1, key="new_diff")

            if st.form_submit_button("✅ 새 문제 추가하기"):
                new_q_html = st.session_state.temp_new_question
                if not new_q_html or not new_q_html.strip() or new_q_html == '<p><br></p>': 
                    st.error("질문 내용을 입력해야 합니다.")
                elif not valid_options: 
                    st.error("선택지 내용을 입력해야 합니다.")
                elif not new_answer: 
                    st.error("정답을 선택해야 합니다.")
                else:
                    media_url, media_type = None, None
                    if uploaded_file:
                        file_path = os.path.join(MEDIA_DIR, uploaded_file.name)
                        with open(file_path, "wb") as f: f.write(uploaded_file.getbuffer())
                        media_url, media_type = file_path, 'image' if uploaded_file.type.startswith('image') else 'video'

                    final_options = {k: v for k, v in st.session_state.temp_new_options.items() if k in valid_options}

                    new_id = add_new_original_question(new_q_html, final_options, new_answer, new_difficulty, media_url, media_type)

                    st.session_state.temp_new_question = ""
                    st.session_state.temp_new_options = {}
                    st.toast(f"성공! 새 문제(ID: {new_id})가 추가되었습니다.", icon="🎉")
                    st.rerun()

    with tabs[3]: #문제 편집
        st.subheader("✏️ 문제 편집")
        all_ids = get_all_question_ids('original')
        if not all_ids:
            st.info("편집할 문제가 없습니다.")
        else:
            # --- 모달 상태 변수 추가 ---
            # 모달이 열려 있는지 여부를 직접 제어하는 상태 변수
            if 'show_delete_modal' not in st.session_state:
                st.session_state.show_delete_modal = False
            
            # 어떤 문제를 삭제할지 ID를 저장할 세션 상태
            if 'question_to_delete_id' not in st.session_state:
                st.session_state.question_to_delete_id = None

             # 어떤 문제를 삭제할지 ID를 저장할 세션 상태
            if 'question_to_delete_id' not in st.session_state:
                st.session_state.question_to_delete_id = None

            if 'current_edit_id' not in st.session_state: 
                st.session_state.current_edit_id = all_ids[0]
            
            def change_id(amount):
                try:
                    curr_idx = all_ids.index(st.session_state.current_edit_id)
                    st.session_state.current_edit_id = all_ids[(curr_idx + amount) % len(all_ids)]
                except ValueError: st.session_state.current_edit_id = all_ids[0]
            c1, c2, c3 = st.columns([1, 2, 1])
            c1.button("◀️ 이전", on_click=change_id, args=(-1,), use_container_width=True)
            c2.selectbox("문제 ID 선택", options=all_ids, key="current_edit_id", label_visibility="collapsed")
            c3.button("다음 ▶️", on_click=change_id, args=(1,), use_container_width=True)
            edit_id = st.session_state.current_edit_id
            q_data = get_question_by_id(edit_id, 'original')

            if q_data:
                form_cols = st.columns([0.8, 0.2])
                with form_cols[0]:
                    st.markdown(f"**ID {edit_id} 문제 수정:**")
                with form_cols[1]:
                    def open_delete_modal(q_id):
                        st.session_state.question_to_delete_id = q_id
                        st.session_state.show_delete_modal = True    
                    
                    st.button(
                        "이 문제 삭제 🗑️", 
                        use_container_width=True, 
                        type="secondary",
                        on_click=open_delete_modal,
                        args=(edit_id,)
                    )       

                with st.form(key=f"edit_form_{edit_id}"):
                    st.markdown(f"**ID {edit_id} 수정:**")
                    curr_opts = json.loads(q_data['options'])
                    curr_ans = json.loads(q_data['answer'])
                    edited_q = st_quill(value=q_data['question'] or "", html=True, key=f"q_{edit_id}")
                    
                    if q_data.get('media_url'): st.write(f"현재 미디어: {os.path.basename(q_data['media_url'])}")
                    edited_file = st.file_uploader("미디어 교체", key=f"f_{edit_id}")
                    edited_opts = {k: st.text_input(f"선택지 {k}:", value=v, key=f"o_{k}_{edit_id}") for k, v in curr_opts.items()}
                    edited_ans = st.multiselect("정답:", options=list(edited_opts.keys()), default=curr_ans, key=f"a_{edit_id}")
                    st.write("---") # 시각적 구분을 위한 선
                    st.markdown("**난이도 수정**")
                    
                    difficulty_options = ['쉬움', '보통', '어려움']
                    # DB에서 현재 문제의 난이도를 가져옴
                    current_difficulty = q_data.get('difficulty', '보통')
                    # 만약 DB 값이 옵션 목록에 없으면 '보통'으로 강제 (안정성)
                    if current_difficulty not in difficulty_options:
                        current_difficulty = '보통'
                    
                    current_difficulty_index = difficulty_options.index(current_difficulty)
                    
                    edited_difficulty = st.selectbox(
                        "난이도:", 
                        difficulty_options, 
                        index=current_difficulty_index, 
                        key=f"edit_diff_{edit_id}"
                    )
                    
                    if st.form_submit_button("저장"):
                        m_url, m_type = q_data.get('media_url'), q_data.get('media_type')
                        if edited_file:
                            fp = os.path.join(MEDIA_DIR, edited_file.name)
                            with open(fp, "wb") as f: f.write(edited_file.getbuffer())
                            m_url, m_type = fp, 'image' if edited_file.type.startswith('image') else 'video'
                        update_original_question(edit_id, edited_q, edited_opts, edited_ans, edited_difficulty, m_url, m_type)
                        st.toast("업데이트 완료!", icon="✅")
                        st.cache_data.clear()
                        st.rerun()
            
            # Modal 객체는 항상 생성하되, 열고 닫는 것은 우리 상태 변수로 제어
            delete_question_modal = Modal(title="⚠️ 문제 삭제 확인", key="delete_question_modal")            

            # st.session_state.show_delete_modal이 True일 때만 모달을 엶
            if st.session_state.show_delete_modal:
                with delete_question_modal.container():
                    delete_id = st.session_state.question_to_delete_id
                    st.warning(f"정말로 ID {delete_id} 문제를 영구적으로 삭제하시겠습니까?")
                    
                    m_c1, m_c2 = st.columns(2)
                    if m_c1.button("✅ 예, 삭제합니다", type="primary", use_container_width=True):
                        delete_single_original_question(delete_id)
                        st.toast(f"ID {delete_id} 문제가 삭제되었습니다.", icon="🗑️")
                        
                        # 삭제 후 상태 초기화 및 다음 문제로 이동
                        st.session_state.question_to_delete_id = None
                        st.session_state.show_delete_modal = False # ★ 모달 닫기
                        
                        remaining_ids = get_all_question_ids('original')
                        st.session_state.current_edit_id = remaining_ids[0] if remaining_ids else None
                        
                        st.rerun() # 모든 상태 변경 후 마지막에 한 번만 rerun
                    
                    if m_c2.button("❌ 아니요, 취소합니다", use_container_width=True):
                        st.session_state.question_to_delete_id = None
                        st.session_state.show_delete_modal = False # ★ 모달 닫기
                        st.rerun()

    # --- 탭 4: 오답 노트 관리 ---
    with tabs[4]:
        st.subheader("📒 오답 노트 관리")
        wrong_answers = get_wrong_answers(username)

        if not wrong_answers:
            st.info("관리할 오답 노트가 없습니다.")
        else:
            st.warning(f"총 {len(wrong_answers)}개의 오답 기록이 있습니다. 완전히 이해한 문제는 삭제할 수 있습니다.")
            # 삭제 확인 모달 초기화
            wrong_modal = Modal(title="⚠️ 오답 기록 삭제 확인", key="delete_wrong_modal")
            if 'delete_wrong_target' not in st.session_state: st.session_state.delete_wrong_target = None

            # 각 항목을 하나의 expander로 그리고 삭제 버튼 키에 인덱스를 포함해 고유화
            for i, row in enumerate(wrong_answers):
                # sqlite3.Row일 수 있으므로 안전하게 dict로 변환
                try:
                    question = dict(row)
                except Exception:
                    question = row

                q_id = question.get('id') or question.get('question_id')
                q_type = question.get('question_type') or question.get('type') or 'original'
                preview = (question.get('question') or "").replace('<p>', '').replace('</p>', '')[:50].strip() + "..."

                # expander 옆에 작게 삭제 버튼을 배치 (한 줄로 보여주기 위해 container + columns 사용)
                with st.container():
                    col_exp, col_btn = st.columns([0.95, 0.05])
                    with col_exp:
                        with st.expander(f"**ID {q_id} ({q_type})** | {preview}"):
                            st.markdown(question.get('question') or "", unsafe_allow_html=True)
                            try:
                                options = json.loads(question.get('options') or "{}")
                                answer = json.loads(question.get('answer') or "[]")
                                st.write("**선택지:**")
                                for key, value in options.items():
                                    st.write(f" - **{key}:** {value}")
                                st.error(f"**정답:** {', '.join(answer)}")
                            except (json.JSONDecodeError, TypeError):
                                st.write("선택지 또는 정답 정보를 불러올 수 없습니다.")
                    with col_btn:
                        small_key = f"del_wrong_btn_{q_id}_{q_type}_{i}"
                        if st.button("삭제", key=small_key, help="오답 기록 삭제", use_container_width=True):
                            st.session_state.delete_wrong_target = (q_id, q_type)
                            wrong_modal.open()
 
                # 모달이 열리면 확인 UI 그림
                if wrong_modal.is_open():
                    with wrong_modal.container():
                        target = st.session_state.get('delete_wrong_target')
                        if target:
                            st.warning(f"정말로 ID {target[0]} ({target[1]}) 오답 기록을 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.")
                            c1, c2 = st.columns(2)
                            if c1.button("✅ 예, 삭제합니다", type="primary"):
                                delete_wrong_answer(username, target[0], target[1])
                                st.toast("오답 기록이 삭제되었습니다.", icon="🗑️")
                                st.session_state.delete_wrong_target = None
                                wrong_modal.close()
                                st.rerun()
                            if c2.button("❌ 취소", use_container_width=True):
                                st.session_state.delete_wrong_target = None
                                wrong_modal.close()
                                st.rerun()

    # --- 탭 5: AI 변형 문제 관리 ---
    with tabs[5]:
        st.subheader("✨ AI 변형 문제 관리")
        modified_questions = get_all_modified_questions()
        if not modified_questions:
            st.info("관리할 AI 변형 문제가 없습니다.")
        else:
            # 전체 삭제 확인 모달
            mod_modal = Modal(title="⚠️ 변형 문제 삭제 확인", key="delete_mod_modal")
            if st.button("모든 변형 문제 삭제", type="primary"):
                st.session_state.delete_mod_target = "ALL"
                mod_modal.open()

            # 각 항목별 삭제 버튼 -> 모달
            if 'delete_mod_target' not in st.session_state: st.session_state.delete_mod_target = None
            single_mod_modal = Modal(title="⚠️ 변형 문제 삭제 확인", key="delete_single_mod_modal")
            for idx, mq in enumerate(modified_questions):
                # expander + 우측 작고 눈에 거슬리지 않는 삭제 버튼 배치
                preview = mq['question'].replace('<p>', '').replace('</p>', '')[:50].strip() + "..."
                with st.container():
                    col_exp, col_btn = st.columns([0.95, 0.05])
                    with col_exp:
                        with st.expander(f"**ID {mq['id']}** | {preview}"):
                            st.markdown(mq['question'], unsafe_allow_html=True)
                            try:
                                options = json.loads(mq['options'])
                                answer = json.loads(mq['answer'])
                                st.write("**선택지:**")
                                for key, value in options.items():
                                    st.write(f" - **{key}:** {value}")
                                st.error(f"**정답:** {', '.join(answer)}")
                            except (json.JSONDecodeError, TypeError):
                                st.write("선택지 또는 정답 정보를 불러올 수 없습니다.")

                    with col_btn:
                        mod_btn_key = f"del_mod_btn_{mq['id']}_{idx}"
                        if st.button("삭제", key=mod_btn_key, help="변형 문제 삭제", use_container_width=True):
                            st.session_state.delete_mod_target = mq['id']
                            single_mod_modal.open()

            if single_mod_modal.is_open():
                with single_mod_modal.container():
                    target = st.session_state.get('delete_mod_target')
                    if target:
                        st.warning(f"정말로 ID {target} 변형 문제를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.")
                        c1, c2 = st.columns(2)
                        if c1.button("✅ 예, 삭제", type="primary"):
                            delete_modified_question(target)
                            st.toast("변형 문제가 삭제되었습니다.", icon="🗑️")
                            st.session_state.delete_mod_target = None
                            single_mod_modal.close()
                            st.rerun()
                        if c2.button("❌ 취소"):
                            st.session_state.delete_mod_target = None
                            single_mod_modal.close()
                            st.rerun()

    # --- 탭 6: AI 해설 관리 탭 ---
    with tabs[6]: # AI 해설 관리 탭
        st.subheader("💾 저장된 AI 해설 관리")
        st.info("저장된 AI 해설을 확인하고, 불필요한 해설을 삭제할 수 있습니다.")
        
        all_explanations = get_all_explanations_for_admin()
        if not all_explanations:
            st.write("저장된 AI 해설이 없습니다.")
        else:
            for exp_info in all_explanations:
                q_id = exp_info['question_id']
                q_type = exp_info['question_type']
                question = get_question_by_id(q_id, q_type)

                if question:
                    with st.expander(f"**문제 ID: {q_id} ({q_type})** | {question['question'].replace('<p>', '').replace('</p>', '')[:50].strip()}..."):
                        
                        explanation = get_ai_explanation_from_db(q_id, q_type)
                        
                        if explanation and "error" not in explanation:
                            st.info(f"**💡 쉬운 비유:**\n\n{explanation.get('analogy', 'N/A')}")
                            st.info(f"**🖼️ 텍스트 시각화:**\n\n```\n{explanation.get('visualization', 'N/A')}\n```")
                            st.info(f"**🔑 핵심 개념 정리:**\n\n{explanation.get('core_concepts', 'N/A')}")
                        else:
                            st.warning("저장된 해설을 불러오는 데 실패했습니다.")

                        # 삭제 버튼
                        if st.button("이 해설 삭제", key=f"del_exp_{q_id}_{q_type}", type="secondary"):
                            delete_ai_explanation(q_id, q_type)
                            st.toast("해설이 삭제되었습니다.", icon="🗑️")
                            st.rerun()

def render_analytics_page(username):
    st.header("📈 학습 통계")
    total, correct, accuracy = get_stats(username)
    c1, c2, c3 = st.columns(3)
    c1.metric("총 풀이", f"{total}")
    c2.metric("정답", f"{correct}")
    c3.metric("정답률", f"{accuracy:.1f}%")
    st.write("---")
    st.subheader("자주 틀리는 문제 Top 5")
    df = get_top_5_missed(username)
    if df.empty: st.info("데이터가 부족합니다.")
    else:
        for _, row in df.iterrows():
            with st.container(border=True):
                st.write(f"**{row['wrong_count']}회 오답** (ID: {row['id']})")
                st.markdown(row['question'], unsafe_allow_html=True)

def render_ai_tutor_page(username):
    """AI 튜터 Q&A 페이지 """
    st.header("🤖 AI 튜터 Q&A")
    st.info("Oracle OCP 또는 데이터베이스 관련 개념에 대해 자유롭게 질문하세요.")

    # --- 1. 세션 상태 초기화 ---
    if "chat_session_id" not in st.session_state:
        st.session_state.chat_session_id = None
    if "editing_message_id" not in st.session_state:
        st.session_state.editing_message_id = None
    if "editing_title_sid" not in st.session_state: # 어떤 세션의 제목을 편집 중인지 ID로 관리
        st.session_state.editing_title_sid = None

    # --- 2. 채팅 세션 관리 사이드바 ---
    with st.sidebar:
        st.write("---")
        st.subheader("대화 기록")
        
        if st.button("새 대화 시작 ➕", use_container_width=True):
            import uuid
            # 새 ID를 생성하고 즉시 현재 세션으로 설정
            st.session_state.chat_session_id = f"session_{uuid.uuid4()}"
            st.session_state.editing_message_id = None
            st.session_state.editing_title = False
            st.rerun()

        st.write("---")
        
        # ★★★ DB에서 항상 최신 세션 목록을 가져옴 ★★★
        chat_sessions = get_chat_sessions(username)


        # --- 통합된 대화 기록 UI ---
        for session_row in chat_sessions:
            session = dict(session_row)
            session_id = session['session_id']
            
            # 현재 선택된 세션이면 다른 배경색으로 강조
            with st.container(border=(session_id == st.session_state.chat_session_id)):
                col1, col2, col3 = st.columns([0.7, 0.15, 0.15])
                
                with col1:
                    # 현재 편집 중인 세션이면 text_input을, 아니면 버튼을 표시
                    if st.session_state.editing_title_sid == session_id:
                        new_title = st.text_input(
                            "대화 제목 수정:", value=session.get('session_title', ''), 
                            key=f"title_input_{session_id}", label_visibility="collapsed"
                        )
                        if new_title != session.get('session_title', ''):
                            update_chat_session_title(username, session_id, new_title)
                            st.rerun() # 제목 변경 후 즉시 UI 갱신
                    else:
                        title = session.get('session_title') or (session.get('content', '새 대화')[:20] + "...")
                        if st.button(title, key=f"session_btn_{session_id}", use_container_width=True):
                            st.session_state.chat_session_id = session_id
                            st.session_state.editing_message_id = None
                            st.session_state.editing_title_sid = None # 다른 세션 선택 시 편집 모드 해제
                            st.rerun()
                
                with col2:
                    # 편집 버튼 또는 완료 버튼
                    if st.session_state.editing_title_sid == session_id:
                        if st.button("✅", key=f"save_title_{session_id}", help="수정 완료"):
                            st.session_state.editing_title_sid = None
                            st.rerun()
                    else:
                        if st.button("✏️", key=f"edit_title_{session_id}", help="제목 수정"):
                            st.session_state.editing_title_sid = session_id
                            st.rerun()

                with col3:
                    if st.button("🗑️", key=f"del_session_{session_id}", help="대화 삭제"):
                        delete_chat_session(username, session_id)
                        if st.session_state.chat_session_id == session_id:
                            st.session_state.chat_session_id = None
                        st.rerun()

    # --- 3. 메인 채팅 화면 ---
    session_id = st.session_state.chat_session_id

    if not session_id: # 세션 ID가 없는 엣지 케이스 처리
        st.warning("채팅 세션을 불러올 수 없습니다. 새 대화를 시작해주세요.")
        return
    
    full_chat_history = get_full_chat_history(username, session_id)
    chat_history_for_api = [{"role": msg['role'], "parts": [msg['content']]} for msg in full_chat_history]
    chat_sessions = get_chat_sessions(username)
    
    # --- 4. 제목 자동 생성 및 표시/편집 UI ---
    current_session_row = next((s for s in chat_sessions if s['session_id'] == session_id), None)
    current_session = dict(current_session_row) if current_session_row else None

    # 이제 current_session은 안전한 파이썬 딕셔너리이거나 None입니다.
    has_title = current_session and current_session.get('session_title')
    
    # 조건: 메시지가 있고, 제목이 아직 없을 때만 AI 호출
    if full_chat_history and not has_title:
        with st.spinner("AI가 대화 제목을 생성 중입니다..."):
            new_title = generate_session_title(chat_history_for_api)
            if new_title:
                update_chat_session_title(username, session_id, new_title)
                st.rerun() # 제목 생성 후 즉시 UI 갱신

    display_title = "새로운 대화" # 기본 제목
    if current_session:
        # .get()을 안전하게 사용하여 제목 표시
        display_title = current_session.get('session_title') or (current_session.get('content', '새 대화')[:30] + "...")

    # --- 5. 화면에 대화 기록 및 편집/삭제 UI 렌더링 ---
    for i, message in enumerate(full_chat_history):
        is_user = message['role'] == "user"
        with st.chat_message("user" if is_user else "assistant"):         
            if st.session_state.editing_message_id == message['id']:

                # 편집 UI
                edited_content = st.text_area("메시지 수정:", value=message['content'], key=f"edit_content_{message['id']}")
                c1, c2 = st.columns(2)
                
                # on_click 콜백을 사용하여 상태를 명확하게 전달
                def set_resubmit_info(msg_id, content):
                    st.session_state.resubmit_info = {'id': msg_id, 'content': content}

                if c1.button("✅ 수정 후 다시 질문", key=f"resubmit_{message['id']}", on_click=set_resubmit_info, args=(message['id'], edited_content)):
                    # 1. 수정된 질문을 session_state에 임시 저장
                    st.session_state.edited_question_info = {
                        "id": message['id'],
                        "content": edited_content
                    }
                    # 2. 편집 상태 종료
                    st.session_state.editing_message_id = None
                    # 3. rerun하여 페이지 하단에서 후속 처리
                    st.rerun()

                if c2.button("❌ 취소", key=f"cancel_edit_{message['id']}"):
                    st.session_state.editing_message_id = None
                    st.rerun()
            else:
                # 일반 메시지 표시
                col1, col2, col3 = st.columns([0.8, 0.1, 0.1])
                with col1:
                    st.markdown(message['content'])
                if is_user:
                    with col2:
                        if st.button("✏️", key=f"edit_btn_{message['id']}", help="이 메시지 수정"):
                            st.session_state.editing_message_id = message['id']
                            st.rerun()
                with col3:
                    if st.button("🗑️", key=f"del_msg_{message['id']}", help="이 메시지 삭제"):
                         # DB 함수가 이제 남은 메시지가 있는지 여부를 반환
                        session_has_messages_left = delete_single_chat_message(message['id'], username, session_id)
                    
                        if not session_has_messages_left:
                            # 남은 메시지가 없으면 세션 자체를 삭제
                            st.toast("모든 메시지가 삭제되어 대화가 종료되었습니다.")
                            delete_chat_session(username, session_id)
                            st.session_state.chat_session_id = None # 현재 세션 ID 초기화
                        else:
                            st.toast("메시지가 삭제되었습니다.")
                        st.rerun()

    # --- 6. 사용자 입력 및 AI 응답 처리  ---
    # Case 1: '수정 후 다시 질문' 버튼이 눌렸는지 먼저 확인
    if 'edited_question_info' in st.session_state and st.session_state.edited_question_info:
        info = st.session_state.pop('edited_question_info') # 정보 사용 후 즉시 제거
        msg_id_to_edit = info['id']
        edited_content = info['content']
        
        # 1. DB 업데이트
        update_chat_message(msg_id_to_edit, edited_content)
        if full_chat_history and msg_id_to_edit == full_chat_history[0]['id']:
            update_chat_session_title(username, session_id, edited_content[:30])
        
        # 2. 수정 지점 이후 메시지 삭제
        delete_chat_messages_from(msg_id_to_edit, username, session_id)
        
        # 3. AI 호출
        with st.spinner("AI가 수정된 질문에 대한 답변을 생성 중입니다..."):
            current_history = get_chat_history(username, session_id)
            from gemini_handler import get_chat_response
            response = get_chat_response(current_history, edited_content)
            save_chat_message(username, session_id, "model", response)
            
        # 4. 모든 작업 후 UI 새로고침
        st.rerun()

    # Case 2: '수정 후 다시 질문'이 아닐 경우, 새로운 질문 입력을 처리
    else:
        prompt = st.chat_input("질문을 입력하세요...")
        if prompt:
            is_first_message = not full_chat_history
            
            # 1. 새 사용자 메시지 저장
            save_chat_message(username, session_id, "user", prompt, session_title=prompt if is_first_message else None)
            
            # 2. AI 호출
            with st.spinner("AI가 답변을 생각 중입니다..."):
                current_history = get_chat_history(username, session_id)
                from gemini_handler import get_chat_response
                response = get_chat_response(current_history, prompt)
                save_chat_message(username, session_id, "model", response)
            
            # 3. 모든 작업 후 UI 새로고침
            st.rerun()

# --- Main App Entry Point ---
def run_main_app(authenticator, all_user_info):
    """로그인 성공 후 실행되는 메인 앱 로직."""
    username = st.session_state.get("username")
    name = st.session_state.get("name")
    initialize_session_state()
    st.title("🚀 Oracle OCP AI 튜터")
    st.session_state.is_admin = (all_user_info.get(username, {}).get('role') == 'admin')

    with st.sidebar:
        st.title(f"환영합니다, {name}님!")
        if st.button("로그아웃", key="main_logout"):
            for k in ["authentication_status", "username", "name", "is_admin"]:
                if k in st.session_state: del st.session_state[k]
            st.rerun()
        st.write("---")
        st.title("메뉴")
        
        menu_items = { "home": "📝 퀴즈 풀기", "tutor": "🤖 AI 튜터 Q&A", "notes": "📒 오답 노트", "analytics": "📈 학습 통계", "manage": "⚙️ 설정 및 관리" }
        for view_key, label in menu_items.items():
            button_type = "primary" if st.session_state.current_view == view_key else "secondary"
            if st.button(label, use_container_width=True, type=button_type):
                if st.session_state.current_view != view_key:
                    st.session_state.current_view = view_key
                    if view_key == 'home':
                        st.session_state.questions_to_solve = []
                        st.session_state.user_answers = {}
                        st.session_state.current_question_index = 0
                    st.rerun()

        st.write("---")
        st.subheader("앱 관리")
        if st.button("현재 학습 초기화", use_container_width=True):
            keys_to_keep = ['authentication_status', 'name', 'username', 'logout', 'db_setup_done', 'current_view']
            for key in list(st.session_state.keys()):
                if key not in keys_to_keep: del st.session_state[key]
            st.toast("현재 학습 상태가 초기화되었습니다.", icon="🔄")
            st.rerun()
        with st.expander("⚠️ 전체 데이터 초기화"):
            st.warning("로그인한 사용자의 모든 오답 기록과 (관리자인 경우) AI 변형 문제를 영구적으로 삭제합니다.")
            if st.button("모든 학습 기록 삭제", type="primary", use_container_width=True):
                conn = get_db_connection()
                conn.execute("DELETE FROM user_answers WHERE username = ?", (username,))
                conn.commit()
                conn.close()
                if st.session_state.is_admin:
                    clear_all_modified_questions()
                    st.toast("모든 AI 변형 문제가 삭제되었습니다.", icon="💥")
                st.toast(f"{name}님의 모든 학습 기록이 삭제되었습니다.", icon="🗑️")
                st.session_state.clear()
                st.rerun()
        
    view_map = {
        "home": render_home_page, "tutor": lambda: render_ai_tutor_page(username), "quiz": render_quiz_page, "results": render_results_page,
        "notes": render_notes_page, "manage": render_management_page, "analytics": render_analytics_page,
    }
    render_func = view_map.get(st.session_state.current_view, render_home_page)
    
    if render_func:
        views_requiring_username = ['notes', 'manage', 'analytics', 'results']
        if st.session_state.current_view in views_requiring_username:
            render_func(username=username)
        else:
            render_func()

# --- 7. Main Application Entry Point ---
def main():
    """메인 실행 함수: 앱의 시작점"""
    st.set_page_config(page_title="Oracle OCP AI 튜터", layout="wide", initial_sidebar_state="expanded")

    # --- 1. 데이터베이스 및 마스터 계정 설정 ---
    if 'db_setup_done' not in st.session_state:
        setup_database_tables()
        credentials, _ = fetch_all_users()
        if MASTER_ACCOUNT_USERNAME not in credentials.get('usernames', {}):
            hashed_pw = bcrypt.hashpw(MASTER_ACCOUNT_PASSWORD.encode(), bcrypt.gensalt()).decode()
            ensure_master_account(MASTER_ACCOUNT_USERNAME, MASTER_ACCOUNT_NAME, hashed_pw)
            st.toast(f"관리자 계정 '{MASTER_ACCOUNT_USERNAME}' 설정 완료!", icon="👑")
        st.session_state.db_setup_done = True

    # --- 2. 인증 객체 생성 ---
    credentials, all_user_info = fetch_all_users()
    authenticator = None  # 이전 객체 호환성 위해 변수는 남겨둠

    # --- 3. 로그인 처리 (세로 레이아웃: 타이틀 -> 로그인 -> 회원가입) ---
    name = st.session_state.get("name")
    authentication_status = st.session_state.get("authentication_status")
    username = st.session_state.get("username")

    if not authentication_status:
        st.title("🚀 Oracle OCP AI 튜터")
        st.markdown("로그인하거나 새 계정을 만들어주세요.")

        st.subheader("로그인")
        login_user = st.text_input("아이디", key="login_username")
        login_pw = st.text_input("비밀번호", type="password", key="login_password")
        if st.button("로그인"):
            user = all_user_info.get(login_user)
            if user and user.get("password") and bcrypt.checkpw(login_pw.encode(), user["password"].encode()):
                st.session_state.authentication_status = True
                st.session_state.username = login_user
                st.session_state.name = user.get("name", login_user)
                st.session_state.is_admin = (user.get("role") == "admin")
                st.success("로그인 성공")
                st.rerun()
            else:
                st.error("아이디 또는 비밀번호가 일치하지 않습니다.")

        st.write("---")
        # 회원가입은 접었다 폈다 가능한 expander로 제공
        with st.expander("새 계정 만들기 (이름 · 아이디 · 비밀번호)", expanded=False):
            reg_name = st.text_input("이름", key="reg_name")
            reg_user = st.text_input("아이디", key="reg_user")
            reg_pw = st.text_input("비밀번호", type="password", key="reg_pw")
            if st.button("회원가입", key="signup_btn"):
                if not all((reg_name, reg_user, reg_pw)):
                    st.error("모든 필드를 입력해주세요.")
                elif reg_user == MASTER_ACCOUNT_USERNAME:
                    st.error(f"'{MASTER_ACCOUNT_USERNAME}'은 예약된 아이디입니다.")
                elif reg_user in all_user_info:
                    st.error("이미 존재하는 아이디입니다.")
                else:
                    hashed_pw = bcrypt.hashpw(reg_pw.encode(), bcrypt.gensalt()).decode()
                    success, msg = add_new_user(reg_user, reg_name, hashed_pw)
                    if success:
                        st.success("회원가입 완료! 로그인해주세요.")
                    else:
                        st.error(msg)
        # 로그인되지 않은 상태면 main 흐름 멈춤
        return

    # --- 4. 로그인 상태에 따른 분기 (로그인 완료 시) ---
    if authentication_status:
        run_main_app(authenticator, all_user_info)

# --- 8. Script Execution Block ---
if __name__ == "__main__":
    main()