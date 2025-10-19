# app.py

"""
Oracle OCP AI 튜터 메인 애플리케이션 파일
"""
import streamlit as st
import streamlit_authenticator as stauth
import bcrypt
import random
import json
import os
from dotenv import load_dotenv
from streamlit_quill import st_quill
from streamlit_modal import Modal

# --- Custom Modules ---
# 순서: 의존성이 없는 모듈부터 임포트
from gemini_handler import generate_explanation, generate_modified_question, analyze_difficulty
from db_utils import * 
from ui_components import display_question, display_results

# --- Constants ---
load_dotenv()
MEDIA_DIR = "media"
if not os.path.exists(MEDIA_DIR):
    os.makedirs(MEDIA_DIR)
MASTER_ACCOUNT_USERNAME = "admin"
MASTER_ACCOUNT_NAME = "Master Admin"
# 코드에서 비밀번호를 직접 적는 대신, os.environ.get()으로 환경 변수를 읽어옵니다.
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

    for question in wrong_answers:
        question = get_question_by_id(question['question_id'], question['question_type'])
        if question:
            with st.expander(f"**ID {question['id']} ({question['question_type']})** | {question['question'].replace('<p>', '').replace('</p>', '')[:50].strip()}..."):
                
                # --- 펼쳤을 때 보일 상세 내용 ---
                st.markdown("**질문:**")
                st.markdown(question['question'], unsafe_allow_html=True)

                if question.get('media_url') and os.path.exists(question.get('media_url')):
                    if question.get('media_type') == 'image': st.image(question['media_url'])
                    else: st.video(question['media_url'])
                
                try:
                    options = json.loads(question['options'])
                    st.markdown("**선택지:**")
                    for key, value in options.items():
                        st.write(f" - **{key}:** {value}")
                except (json.JSONDecodeError, TypeError):
                    st.write("선택지를 불러올 수 없습니다.")
                
                try:
                    answer = json.loads(question['answer'])
                    st.error(f"**정답:** {', '.join(answer)}")
                except (json.JSONDecodeError, TypeError):
                    st.error("정답 정보를 불러올 수 없습니다.")

                if st.button("🤖 AI 해설", key=f"note_exp_{question['id']}_{question['question_type']}"):
                    with st.spinner("해설 생성 중..."):
                        if exp := get_ai_explanation(question['id'], question['question_type']):
                            if err := exp.get('error'): st.error(err)
                            else:
                                st.info(f"**💡 쉬운 비유:**\n{exp.get('analogy', 'N/A')}")
                                st.info(f"**🔑 핵심 개념:**\n{exp.get('core_concepts', 'N/A')}")

def render_results_page(username):
    display_results(username, get_ai_explanation)
    if st.button("새 퀴즈 시작"): st.session_state.current_view = 'home'; st.rerun()

def render_management_page(username):
    """
    문제 추가/편집, 오답 노트, 사용자 관리 등 앱의 설정 및 데이터 관리 화면을 렌더링합니다.
    관리자와 일반 사용자에 따라 다른 탭을 표시합니다.
    """
    st.header("⚙️ 설정 및 관리")
    is_admin = st.session_state.get('is_admin', False)

    # 공통 탭과 조건부 탭 목록 정의
    common_tab_list = ["원본 문제 데이터", "문제 추가", "문제 편집", "오답 노트 관리", "AI 변형 문제 관리"]
    if is_admin:
        tab_list = ["👑 사용자 관리"] + common_tab_list
    else:
        tab_list = ["👋 회원 탈퇴"] + common_tab_list
    
    # st.tabs를 한 번만 호출하여 모든 탭 객체를 리스트로 받음
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
        st.subheader("📚 원본 문제 데이터")
        col1, col2 = st.columns(2)
        with col1:
            st.info("JSON 파일의 문제를 DB로 불러오거나, DB의 문제를 초기화합니다.")
            num_q = len(get_all_question_ids('original'))
            st.metric("현재 DB에 저장된 문제 수", f"{num_q} 개")
            
            # AI 난이도 분석 옵션
            analyze_option = st.checkbox("🤖 AI로 자동 난이도 분석 실행", value=False)
            
            if st.button("JSON에서 문제 불러오기", type="primary"):
                try:
                    with open('questions_final.json', 'r', encoding='utf-8') as f:
                        questions_from_json = json.load(f)
                except FileNotFoundError:
                    st.error("`questions_final.json` 파일을 찾을 수 없습니다.")
                    st.stop() # 파일을 못 찾으면 더 이상 진행하지 않음
                
                if not questions_from_json:
                    st.warning("JSON 파일에 문제가 없습니다.")
                else:
                    if analyze_option:
                        # AI 난이도 분석 로직
                        questions_to_load = []
                        progress_bar = st.progress(0, text="AI 난이도 분석 시작...")
                        total_questions = len(questions_from_json)
                        for i, q in enumerate(questions_from_json):
                            difficulty = analyze_difficulty(q['question'])
                            q['difficulty'] = difficulty
                            questions_to_load.append(q)
                            progress_value = (i + 1) / total_questions
                            progress_bar.progress(progress_value, text=f"AI 난이도 분석 중... ({i + 1}/{total_questions})")
                        
                        st.toast("AI 분석 완료! DB에 저장합니다.", icon="🤖")
                        count, error = load_original_questions_from_json(questions_to_load)
                        progress_bar.empty()
                    else:
                        # AI 분석 안 할 때 로직
                        for q in questions_from_json:
                            q['difficulty'] = '보통'
                        count, error = load_original_questions_from_json(questions_from_json)

                    # --- 여기가 핵심 수정 부분 ---
                    # if error: 블록을 st.button 블록 안으로 이동시켰습니다.
                    if error:
                        st.error(f"문제 저장 실패: {error}")
                    else:
                        st.success(f"모든 문제({count}개)를 성공적으로 불러왔습니다!")
                        st.rerun()
                    # --- 여기까지 ---

            with st.expander("⚠️ 문제 초기화 (주의)"):
                if st.button("모든 원본 문제 삭제", type="secondary"):
                    clear_all_original_questions()
                    st.toast("모든 원본 문제가 삭제되었습니다.", icon="🗑️")
                    st.rerun()
        st.write("---")

        with col2:
            st.info("현재 DB 데이터를 JSON 파일로 저장(내보내기)합니다.")
            
            # 1. DB에서 데이터를 가져와 JSON 문자열로 변환
            questions_to_export = export_questions_to_json_format()
            # json.dumps를 사용하여 예쁘게 포맷팅된 문자열로 만듦 (indent=4)
            json_string_to_export = json.dumps(questions_to_export, indent=4, ensure_ascii=False)
            
            st.metric("내보낼 문제 수", f"{len(questions_to_export)} 개")

            # 2. st.download_button을 사용하여 파일 다운로드 기능 제공
            st.download_button(
               label="📥 JSON 파일로 다운로드",
               data=json_string_to_export,
               file_name="questions_updated.json", # 다운로드될 파일 이름
               mime="application/json",
            )

            st.warning("아래 버튼은 서버의 `questions_final.json` 파일을 직접 덮어씁니다.")
            if st.button("서버 파일에 덮어쓰기"):
                try:
                    with open("questions_final.json", "w", encoding="utf-8") as f:
                        f.write(json_string_to_export)
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
                question = get_question_by_id(question['question_id'], question['question_type'])
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
                        if st.button("이 오답 기록 삭제", key=f"del_wrong_manage_{question['question_id']}_{question['question_type']}", type="secondary"):
                            delete_wrong_answer(username, question['question_id'], question['question_type'])
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
    
    # 관리자 여부 확인
    st.session_state.is_admin = (all_user_info.get(username, {}).get('role') == 'admin')

    # 사이드바 렌더링
    st.sidebar.title(f"환영합니다, {name}님!")
    authenticator.logout('로그아웃', 'sidebar', key='main_logout')
    
    initialize_session_state()

    st.sidebar.write("---")
    st.sidebar.title("메뉴")
    menu = {"home": "📝 퀴즈 풀기", "notes": "📒 오답 노트", "analytics": "📈 학습 통계", "manage": "⚙️ 설정 및 관리"}
    for view, label in menu.items():
        if st.sidebar.button(label, use_container_width=True, type="primary" if st.session_state.current_view == view else "secondary"):
            if st.session_state.current_view != view:
                st.session_state.current_view = view
                if view == 'home':
                    st.session_state.questions_to_solve = []
                    st.session_state.user_answers = {}
                    st.session_state.current_question_index = 0
                st.rerun()

    st.sidebar.write("---")
    if st.sidebar.button("학습 초기화", use_container_width=True):
        for k in list(st.session_state.keys()):
            if k not in ['authentication_status', 'name', 'username', 'logout', 'current_view', 'db_setup_done']:
                del st.session_state[k]
        st.toast("초기화되었습니다.", icon="🔄")
        st.rerun()

def main():
    """메인 실행 함수"""
    st.set_page_config(page_title="Oracle OCP AI 튜터", layout="wide", initial_sidebar_state="expanded")

    # --- 1. 앱의 공통 헤더를 먼저 렌더링 ---
    st.title("🚀 Oracle OCP AI 튜터")
    
    # --- 2. DB 및 마스터 계정 설정 (백그라운드 작업) ---
    if 'db_setup_done' not in st.session_state:
        setup_database_tables()
        credentials, _ = fetch_all_users()
        if MASTER_ACCOUNT_USERNAME not in credentials['usernames']:
            hashed_pw = bcrypt.hashpw(MASTER_ACCOUNT_PASSWORD.encode(), bcrypt.gensalt()).decode()
            ensure_master_account(MASTER_ACCOUNT_USERNAME, MASTER_ACCOUNT_NAME, hashed_pw)
            st.toast(f"관리자 계정 '{MASTER_ACCOUNT_USERNAME}' 설정 완료!", icon="👑")
        st.session_state.db_setup_done = True
    
    # --- 3. 인증 객체 생성 ---
    credentials, all_user_info = fetch_all_users()
    authenticator = stauth.Authenticate(credentials, "ocp_cookie", "auth_key", 30)
    authenticator.login(location='main')

    # --- 인증 상태에 따른 화면 분기 ---
    # 로그인 위젯을 메인 영역에 렌더링
    authenticator.login(location='main')

    if st.session_state.get("authentication_status"):
        # --- 로그인 성공 시 ---
        run_main_app(authenticator, all_user_info)

    elif st.session_state.get("authentication_status") is False:
        st.error('아이디 또는 비밀번호가 일치하지 않습니다.')

    elif st.session_state.get("authentication_status") is None:
        st.info('로그인하거나 아래에서 새 계정을 만들어주세요.')
        
        # 회원가입 폼 렌더링
        with st.expander("새 계정 만들기"):
            try:
                if authenticator.register_user('회원가입', preauthorization=False):
                    # 회원가입 성공 후 DB에 저장
                    new_username = st.session_state['username']
                    new_name = st.session_state['name']
                    new_password = st.session_state['password'] # register_user는 평문 비밀번호를 반환
                    
                    hashed_password = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
                    success, msg = add_new_user(new_username, new_name, hashed_password)
                    if success:
                        st.success('회원가입이 완료되었습니다. 이제 로그인해주세요.')
                    else:
                        st.error(msg)
                        # (선택) 가입 실패 시 authenticator 내부 데이터 롤백 필요 (고급)
            except Exception as e:
                st.error(e)

def run_main_app(authenticator, all_user_info):
    """로그인 성공 후 실행되는 메인 앱 로직."""
    username = st.session_state.get("username")
    name = st.session_state.get("name")
    
    # 관리자 여부 확인
    st.session_state.is_admin = (all_user_info.get(username, {}).get('role') == 'admin')

    # 사이드바 렌더링
    with st.sidebar:
        st.title(f"환영합니다, {name}님!")
        authenticator.logout('로그아웃', key='main_logout')
        st.write("---")
        st.title("메뉴")
        # ... (이전 사이드바 버튼 로직)
        
    initialize_session_state()

    # 메인 콘텐츠 렌더링
    view_map = {
        "home": render_home_page,
        "quiz": render_quiz_page,
        "results": lambda: render_results_page(username),
        "notes": lambda: render_notes_page(username),
        "manage": lambda: render_management_page(username),
        "analytics": lambda: render_analytics_page(username),
    }
    render_func = view_map.get(st.session_state.current_view, render_home_page)
    if render_func:
        # username 인자가 필요한 함수에만 전달
        if st.session_state.current_view in ['notes', 'manage', 'analytics', 'results']:
            render_func(username=username)
        else:
            render_func()

# --- 스크립트가 직접 실행될 때만 main() 함수를 호출 ---
if __name__ == "__main__":
    main()