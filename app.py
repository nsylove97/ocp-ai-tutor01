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
from gemini_handler import generate_explanation, generate_modified_question, analyze_difficulty
# db_utils는 함수 단위로 명시적으로 임포트하여 가독성 및 안정성 향상
from db_utils import (
    setup_database_tables, load_original_questions_from_json, get_db_connection,
    get_all_question_ids, get_question_by_id, add_new_original_question, update_original_question,
    get_wrong_answers, delete_wrong_answer, get_all_modified_questions, save_modified_question,
    delete_modified_question, clear_all_modified_questions, get_stats, get_top_5_missed,
    fetch_all_users, add_new_user, delete_user, get_all_users_for_admin, ensure_master_account,
    get_question_ids_by_difficulty, clear_all_original_questions, export_questions_to_json_format
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
@st.cache_data
def get_ai_explanation(_q_id, _q_type):
    question_data = get_question_by_id(_q_id, _q_type)
    if question_data: return generate_explanation(question_data)
    return {"error": f"DB에서 문제(ID: {_q_id}, Type: {_q_type})를 찾을 수 없습니다."}

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
    common_tabs = ["원본 문제 데이터", "문제 추가", "문제 편집", "오답 노트 관리", "AI 변형 문제 관리"]
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
                new_difficulty = st.selectbox("난이도 설정:", ('쉬움', '보통', '어려움'), index=1, key="new_diff")
                if not new_q_html or not new_q_html.strip() or new_q_html == '<p><br></p>': st.error("질문 내용을 입력해야 합니다.")
                elif not valid_options: st.error("선택지 내용을 입력해야 합니다.")
                elif not new_answer: st.error("정답을 선택해야 합니다.")
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
        if not all_ids: st.info("편집할 문제가 없습니다.")
        else:
            if 'current_edit_id' not in st.session_state: st.session_state.current_edit_id = all_ids[0]
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

    # --- 탭 4: 오답 노트 관리 ---
    with tabs[4]:
        st.subheader("📒 오답 노트 관리")
        wrong_answers = get_wrong_answers(username)

        if not wrong_answers:
            st.info("관리할 오답 노트가 없습니다.")
        else:
            st.warning(f"총 {len(wrong_answers)}개의 오답 기록이 있습니다. 완전히 이해한 문제는 삭제할 수 있습니다.")
            for question in wrong_answers:
                if question:
                    with st.expander(f"**ID {question['id']} ({question['question_type']})** | {question['question'].replace('<p>', '').replace('</p>', '')[:50].strip()}..."):
                        
                        st.markdown(question['question'], unsafe_allow_html=True)
                        try:
                            options = json.loads(question['options'])
                            answer = json.loads(question['answer'])
                            st.write("**선택지:**")
                            for key, value in options.items():
                                st.write(f" - **{key}:** {value}")
                            st.error(f"**정답:** {', '.join(answer)}")
                        except (json.JSONDecodeError, TypeError):
                            st.write("선택지 또는 정답 정보를 불러올 수 없습니다.")

                        # 삭제 버튼
                        if st.button("이 오답 기록 삭제", key=f"del_wrong_manage_{question['id']}_{question['question_type']}", type="secondary"):
                            delete_wrong_answer(username, question['id'], question['question_type'])
                            st.toast("삭제되었습니다.", icon="🗑️")
                            st.rerun()


    # --- 탭 5: AI 변형 문제 관리 ---
    with tabs[5]:
        st.subheader("✨ AI 변형 문제 관리")
        modified_questions = get_all_modified_questions()
        if not modified_questions:
            st.info("관리할 AI 변형 문제가 없습니다.")
        else:
            if st.button("모든 변형 문제 삭제", type="primary"):
                clear_all_modified_questions()
                st.toast("모든 AI 변형 문제가 삭제되었습니다.", icon="🗑️")
                st.rerun()

            for mq in modified_questions:
                # --- st.expander 적용 ---
                with st.expander(f"**ID {mq['id']}** | {mq['question'].replace('<p>', '').replace('</p>', '')[:50].strip()}..."):
                    
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
                    
                    # 삭제 버튼
                    if st.button("이 변형 문제 삭제", key=f"del_mod_{mq['id']}", type="secondary"):
                        delete_modified_question(mq['id'])
                        st.toast("삭제되었습니다.", icon="🗑️")
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
        
        menu_items = { "home": "📝 퀴즈 풀기", "notes": "📒 오답 노트", "analytics": "📈 학습 통계", "manage": "⚙️ 설정 및 관리" }
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
        "home": render_home_page, "quiz": render_quiz_page, "results": render_results_page,
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

    # --- 3. 로그인 처리 (간단 커스텀 폼) ---
    name = st.session_state.get("name")
    authentication_status = st.session_state.get("authentication_status")
    username = st.session_state.get("username")

    if not authentication_status:
        st.title("🚀 Oracle OCP AI 튜터")
        st.info("로그인하거나 아래에서 새 계정을 만들어주세요.")

        left, right = st.columns([2, 1])
        with left:
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

        with right:
            with st.expander("새 계정 만들기 (이름, 아이디, 비밀번호만)"):
                reg_name = st.text_input("이름", key="reg_name")
                reg_user = st.text_input("아이디", key="reg_user")
                reg_pw = st.text_input("비밀번호", type="password", key="reg_pw")
                if st.button("회원가입"):
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
        # 로그인되지 않은 상태에서 더 진행하지 않음
        return

    # --- 4. 로그인 상태에 따른 분기 (로그인 완료 시) ---
    if authentication_status:
        run_main_app(authenticator, all_user_info)

# --- 8. Script Execution Block ---
if __name__ == "__main__":
    main()