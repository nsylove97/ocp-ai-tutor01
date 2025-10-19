# app.py
"""
Oracle OCP AI 튜터 메인 애플리케이션 파일
Streamlit을 사용하여 UI를 구성하고, 앱의 전체적인 흐름을 제어합니다.
"""
import streamlit as st
import streamlit_authenticator as stauth
import bcrypt
import random
import json
import os

# --- 3rd Party Libraries ---
from streamlit_quill import st_quill

# --- Custom Modules ---
from gemini_handler import generate_explanation, generate_modified_question
from db_utils import (
    setup_database_tables, load_original_questions_from_json, get_db_connection,
    get_all_question_ids, get_question_by_id,
    add_new_original_question, update_original_question,
    get_wrong_answers, delete_wrong_answer,
    get_all_modified_questions, save_modified_question,
    delete_modified_question, clear_all_modified_questions,
    get_stats, get_top_5_missed,
    setup_database_tables, fetch_all_users, add_new_user,
    delete_user, get_all_users_for_admin, ensure_master_account
)
from ui_components import display_question, display_results

# --- Constants ---
MEDIA_DIR = "media"
if not os.path.exists(MEDIA_DIR):
    os.makedirs(MEDIA_DIR)
MASTER_ACCOUNT_USERNAME = "admin"
MASTER_ACCOUNT_NAME = "admin"
MASTER_ACCOUNT_PASSWORD = "admin"

# --- Helper Functions ---

@st.cache_data
def get_ai_explanation(_q_id, _q_type):
    """문제 ID와 타입을 기반으로 AI 해설을 가져옵니다."""
    question_data = get_question_by_id(_q_id, _q_type)
    if question_data:
        return generate_explanation(question_data)
    return {"error": f"DB에서 문제(ID: {_q_id}, Type: {_q_type})를 찾을 수 없습니다."}

def initialize_session_state():
    """앱의 세션 상태 변수를 초기화합니다."""
    defaults = {
        'current_view': 'home',
        'questions_to_solve': [],
        'current_question_index': 0,
        'user_answers': {},
        'current_edit_id': 1,
        'new_option_count': 5,
        'temp_new_question': "",
        'temp_new_options': {}
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def start_quiz_session(quiz_mode, quiz_type=None, num_questions=None, question_id=None):
    """퀴즈 세션을 시작하기 위한 상태를 설정합니다."""
    st.session_state.questions_to_solve = []
    st.session_state.user_answers = {}
    st.session_state.current_question_index = 0
    questions_loaded = False
    
    if quiz_mode == "랜덤 퀴즈":
        if quiz_type == '기존 문제':
            all_ids = get_all_question_ids('original')
            if all_ids:
                selected_ids = random.sample(all_ids, min(num_questions, len(all_ids)))
                st.session_state.questions_to_solve = [{'id': q_id, 'type': 'original'} for q_id in selected_ids]
                questions_loaded = True
            else:
                st.error("데이터베이스에 원본 문제가 없습니다.")
        elif quiz_type == '✨ AI 변형 문제':
            with st.spinner(f"{num_questions}개의 변형 문제를 생성 중입니다..."):
                original_ids = get_all_question_ids('original')
                if original_ids:
                    selected_original_ids = random.sample(original_ids, min(num_questions, len(original_ids)))
                    newly_generated_q_ids = []
                    for original_id in selected_original_ids:
                        original_question = get_question_by_id(original_id, 'original')
                        if not original_question: continue
                        modified_q_data = generate_modified_question(original_question)
                        if modified_q_data and "error" not in modified_q_data:
                            new_id = save_modified_question(original_id, modified_q_data)
                            newly_generated_q_ids.append(new_id)
                    if newly_generated_q_ids:
                        st.session_state.questions_to_solve = [{'id': q_id, 'type': 'modified'} for q_id in newly_generated_q_ids]
                        questions_loaded = True
                    else:
                        st.error("AI 변형 문제 생성에 실패했습니다.")
                else:
                    st.error("변형할 원본 문제가 없습니다.")
    elif quiz_mode == "ID로 문제 풀기":
        target_question = get_question_by_id(question_id, 'original')
        if target_question:
            st.session_state.questions_to_solve = [{'id': question_id, 'type': 'original'}]
            questions_loaded = True
        else:
            st.error(f"ID {question_id}에 해당하는 원본 문제를 찾을 수 없습니다.")
            
    if questions_loaded:
        st.session_state.current_view = 'quiz'
        st.rerun()

# --- UI Rendering Functions ---

def render_home_page():
    st.header("📝 퀴즈 설정")
    quiz_mode = st.radio("퀴즈 모드를 선택하세요:", ("랜덤 퀴즈", "ID로 문제 풀기"), key="quiz_mode_selector", horizontal=True)

    if quiz_mode == "랜덤 퀴즈":
        num_questions = st.slider("풀고 싶은 문제 수를 선택하세요:", 1, 50, 10, key="num_questions_slider")
        quiz_type = st.radio("어떤 문제를 풀어볼까요?", ('기존 문제', '✨ AI 변형 문제'), key="quiz_type_selector")
        if st.button("랜덤 퀴즈 시작하기", type="primary"):
            start_quiz_session(quiz_mode, quiz_type=quiz_type, num_questions=num_questions)
    else:
        question_id = st.number_input("풀고 싶은 원본 문제의 ID를 입력하세요:", min_value=1, step=1, key="target_question_id")
        if question_id:
            preview_question = get_question_by_id(question_id, 'original')
            if preview_question:
                with st.container(border=True):
                    st.markdown("**미리보기:**")
                    st.markdown(preview_question['question'], unsafe_allow_html=True)
                    if preview_question.get('media_url'):
                        if preview_question.get('media_type') == 'image': st.image(preview_question['media_url'])
                        else: st.video(preview_question['media_url'])
            else:
                st.warning(f"ID {question_id}에 해당하는 문제를 찾을 수 없습니다.")
        if st.button(f"ID {question_id} 문제 풀기", type="primary"):
            start_quiz_session(quiz_mode, question_id=question_id)

def render_quiz_page():
    if not st.session_state.questions_to_solve:
        st.warning("풀 문제가 없습니다. 홈 화면으로 돌아가 퀴즈를 다시 시작해주세요.")
        if st.button("홈으로 돌아가기"):
            st.session_state.current_view = 'home'
            st.rerun()
        return
    idx = st.session_state.current_question_index
    total_questions = len(st.session_state.questions_to_solve)
    st.progress((idx + 1) / total_questions, text=f"{idx + 1}/{total_questions} 문제 진행 중...")
    if idx not in st.session_state.user_answers:
        st.session_state.user_answers[idx] = []
    q_info = st.session_state.questions_to_solve[idx]
    question = get_question_by_id(q_info['id'], q_info['type'])
    if question:
        display_question(question, idx, total_questions)
        col1, _, col2 = st.columns([1, 3, 1])
        with col1:
            if st.button("이전", disabled=(idx == 0), use_container_width=True):
                st.session_state.current_question_index -= 1
                st.rerun()
        with col2:
            if idx < total_questions - 1:
                if st.button("다음", use_container_width=True):
                    st.session_state.current_question_index += 1
                    st.rerun()
            else:
                if st.button("결과 보기", type="primary", use_container_width=True):
                    st.session_state.current_view = 'results'
                    st.rerun()
    else:
        st.error(f"문제(ID: {q_info['id']}, Type: {q_info['type']})를 불러오는 데 실패했습니다.")

def render_notes_page(username):
    st.header("📒 오답 노트")
    wrong_answers = get_wrong_answers(username)
    if not wrong_answers:
        st.success("🎉 축하합니다! 틀린 문제가 없습니다.")
        return
    st.info(f"총 {len(wrong_answers)}개의 틀린 문제가 있습니다.")
    if st.button("틀린 문제 다시 풀기", type="primary"):
        st.session_state.questions_to_solve = [{'id': q['question_id'], 'type': q['question_type']} for q in wrong_answers]
        st.session_state.current_question_index = 0
        st.session_state.user_answers = {}
        st.session_state.current_view = 'quiz'
        st.rerun()
    st.write("---")
    for i, q_info in enumerate(wrong_answers):
        question = get_question_by_id(q_info['question_id'], q_info['question_type'])
        if question:
            with st.container(border=True):
                st.markdown(f"**문제 번호: {question['id']} ({q_info['question_type']})**")
                st.markdown(question['question'], unsafe_allow_html=True)
                if st.button("🤖 AI 해설 보기", key=f"note_exp_{q_info['question_id']}_{i}"):
                    with st.spinner("AI가 열심히 해설을 만들고 있어요..."):
                        explanation = get_ai_explanation(q_info['question_id'], q_info['question_type'])
                        error_msg = explanation.get('error') if explanation else "해설을 가져오지 못했습니다."
                        if error_msg: st.error(error_msg)
                        else:
                            st.info(f"**💡 쉬운 비유:**\n\n{explanation.get('analogy', 'N/A')}")
                            st.info(f"**🖼️ 텍스트 시각화:**\n\n```\n{explanation.get('visualization', 'N/A')}\n```")
                            st.info(f"**🔑 핵심 개념:**\n\n{explanation.get('core_concepts', 'N/A')}")

def render_results_page(username):
    display_results(username, get_ai_explanation)
    if st.button("새 퀴즈 시작하기"):
        st.session_state.current_view = 'home'
        st.rerun()

def render_management_page(username):
    # 관리자인 경우와 일반 사용자인 경우 다른 탭 목록을 보여줌
    if st.session_state.get('is_admin'):
        admin_tabs = ["사용자 관리", "원본 문제 데이터", "문제 추가", "문제 편집", "오답 노트 관리", "AI 변형 문제 관리"]
        tab_admin, tab_data, tab_add, tab_edit, tab_notes, tab_ai = st.tabs(admin_tabs)

        with tab_admin:
            st.subheader("👑 사용자 관리 (관리자 전용)")
            all_users = get_all_users_for_admin()
            st.metric("총 등록된 사용자 수", f"{len(all_users)} 명")
            
            for user in all_users:
                # 관리자 자신은 삭제할 수 없도록 함
                is_master = (user['username'] == MASTER_ACCOUNT_USERNAME)
                
                col1, col2 = st.columns([4, 1])
                with col1:
                    role_icon = "👑" if user['role'] == 'admin' or is_master else "👤"
                    st.write(f"{role_icon} **{user['name']}** ({user['username']})")
                with col2:
                    if not is_master: # 마스터 계정이 아니면 삭제 버튼 표시
                        if st.button("사용자 삭제", key=f"del_user_{user['username']}", type="secondary"):
                            delete_user(user['username'])
                            st.toast(f"사용자 '{user['username']}'가 삭제되었습니다.", icon="🗑️")
                            st.rerun()
    else:
        # 일반 사용자의 탭 목록
        user_tabs = ["회원 탈퇴", "원본 문제 데이터", "문제 추가", "문제 편집", "오답 노트 관리", "AI 변형 문제 관리"]
        tab_탈퇴, tab_data, tab_add, tab_edit, tab_notes, tab_ai = st.tabs(user_tabs)

        with tab_탈퇴:
            st.subheader("👋 회원 탈퇴")
            st.warning("회원 탈퇴 시, 귀하의 모든 학습 기록(오답 노트, 통계 등)이 영구적으로 삭제되며 복구할 수 없습니다.")
            if st.checkbox("위 내용을 확인했으며, 회원 탈퇴에 동의합니다."):
                if st.button("회원 탈퇴 진행하기", type="primary"):
                    delete_user(username)
                    st.success("회원 탈퇴가 완료되었습니다. 이용해주셔서 감사합니다.")
                    # 세션 상태를 초기화하고 로그아웃 처리
                    st.session_state.authentication_status = None
                    st.session_state.name = None
                    st.session_state.username = None
                    st.rerun()
    with tab_data:
        st.subheader("📚 원본 문제 데이터")
        num_questions = len(get_all_question_ids('original'))
        st.metric("현재 저장된 원본 문제 수", f"{num_questions} 개")
        if st.button("JSON에서 원본 문제 불러오기", type="primary"):
            with st.spinner("데이터베이스를 설정하는 중입니다..."):
                count, error = load_original_questions_from_json()
                if error: st.error(f"문제 로딩 실패: {error}")
                else:
                    st.toast(f"성공적으로 {count}개의 문제를 불러왔습니다!")
                    st.rerun()

    with tab_add:
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
            if st.form_submit_button("✅ 새 문제 추가하기"):
                new_q_html = st.session_state.temp_new_question
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
                    new_id = add_new_original_question(new_q_html, final_options, new_answer, media_url, media_type)
                    st.session_state.temp_new_question = ""
                    st.session_state.temp_new_options = {}
                    st.toast(f"성공! 새 문제(ID: {new_id})가 추가되었습니다.", icon="🎉")
                    st.rerun()

    with tab_edit:
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
                    if st.form_submit_button("저장"):
                        m_url, m_type = q_data.get('media_url'), q_data.get('media_type')
                        if edited_file:
                            fp = os.path.join(MEDIA_DIR, edited_file.name)
                            with open(fp, "wb") as f: f.write(edited_file.getbuffer())
                            m_url, m_type = fp, 'image' if edited_file.type.startswith('image') else 'video'
                        update_original_question(edit_id, edited_q, edited_opts, edited_ans, m_url, m_type)
                        st.toast("업데이트 완료!", icon="✅")
                        st.cache_data.clear()
                        st.rerun()

    with tab_notes:
        st.subheader("📒 오답 노트 관리")
        wrong_answers = get_wrong_answers(username)
        if not wrong_answers: st.info("오답 노트가 비어있습니다.")
        else:
            for q_info in wrong_answers:
                q = get_question_by_id(q_info['question_id'], q_info['question_type'])
                if q:
                    c1, c2 = st.columns([4, 1])
                    c1.text(f"ID {q['id']} ({q_info['question_type']}): {q['question'].replace('<p>', '')[:50]}...")
                    if c2.button("삭제", key=f"dw_{q_info['question_id']}_{q_info['question_type']}", type="secondary"):
                        delete_wrong_answer(username, q_info['question_id'], q_info['question_type'])
                        st.toast("삭제되었습니다.", icon="🗑️")
                        st.rerun()

    with tab_ai:
        st.subheader("✨ AI 변형 문제 관리")
        mod_qs = get_all_modified_questions()
        if not mod_qs: st.info("변형 문제가 없습니다.")
        else:
            if st.button("모두 삭제", type="primary"):
                clear_all_modified_questions()
                st.toast("모두 삭제되었습니다.", icon="🗑️")
                st.rerun()
            for mq in mod_qs:
                c1, c2 = st.columns([4, 1])
                c1.text(f"ID {mq['id']}: {mq['question'][:50]}...")
                if c2.button("삭제", key=f"dm_{mq['id']}", type="secondary"):
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
def run_main_app(authenticator):
    """로그인 성공 후의 메인 앱 로직"""
    # session_state에서 직접 사용자 정보 가져오기 (가장 안정적인 방법)
    name = st.session_state.get("name")
    username = st.session_state.get("username")
    st.session_state.is_admin = (username == MASTER_ACCOUNT_USERNAME)

    if not name or not username:
        st.error("사용자 정보를 불러올 수 없습니다. 다시 로그인해주세요.")
        authenticator.logout('로그아웃', location='sidebar', key='err_logout')
        return

    st.sidebar.write(f"환영합니다, **{name}** 님!")
    authenticator.logout('로그아웃', location='sidebar', key='main_logout')
    
    if 'db_setup_done' not in st.session_state:
        setup_database_tables()
        st.session_state.db_setup_done = True

    initialize_session_state()

    st.sidebar.title("메뉴")
    menu = {"home": "📝 퀴즈 풀기", "notes": "📒 오답 노트", "analytics": "📈 학습 통계", "manage": "⚙️ 설정 및 관리"}
    for view, label in menu.items():
        if st.sidebar.button(label, use_container_width=True, type="primary" if st.session_state.current_view == view else "secondary"):
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

    view_map = {
        "home": render_home_page,
        "quiz": render_quiz_page,
        "results": lambda: render_results_page(username),
        "notes": lambda: render_notes_page(username),
        "manage": lambda: render_management_page(username),
        "analytics": lambda: render_analytics_page(username),
    }
    view_map.get(st.session_state.current_view, render_home_page)()

def main():
    st.set_page_config(page_title="Oracle OCP AI 튜터", layout="wide", initial_sidebar_state="expanded")
    
    # --- 1. DB 테이블 구조 확인 및 생성 ---
    if 'db_setup_done' not in st.session_state:
        setup_database_tables()
        st.session_state.db_setup_done = True
    
    # --- 2. 마스터 계정 확인 및 자동 생성 ---
    users = fetch_all_users()
    if MASTER_ACCOUNT_USERNAME not in users['usernames'] or users['usernames'][MASTER_ACCOUNT_USERNAME].get('role') != 'admin':
        hashed_password = bcrypt.hashpw(MASTER_ACCOUNT_PASSWORD.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO users (username, name, password, role) VALUES (?, ?, ?, ?)",
            (MASTER_ACCOUNT_USERNAME, MASTER_ACCOUNT_NAME, hashed_password, 'admin')
        )
        conn.commit()
        conn.close()
        users = fetch_all_users() # 사용자 정보 다시 로드
        st.toast(f"관리자 계정 '{MASTER_ACCOUNT_USERNAME}'이(가) 설정되었습니다.", icon="👑")


    # --- 3. Authenticator 객체 생성 ---
    authenticator = stauth.Authenticate(
        users,
        "ocp_ai_tutor_cookie",
        "abcdef",
        cookie_expiry_days=30
    )

    # --- 4. 로그인 위젯 렌더링 ---
    # st.session_state에 자동으로 'authentication_status', 'name', 'username'이 저장됩니다.
    authenticator.login(location='main')

    # --- 5. 인증 상태에 따라 앱의 흐름을 분기 ---
    if st.session_state.get("authentication_status"):
        # --- 5a. 로그인 성공 시 ---
        # 메인 애플리케이션 로직을 실행합니다.
        run_main_app(authenticator)
    else:
        authenticator.login(location='main')
        if st.session_state["authentication_status"] is False:
            st.error('아이디 또는 비밀번호가 일치하지 않습니다.')
        elif st.session_state["authentication_status"] is None:
            st.info('로그인하거나 새 계정을 만들어주세요.')
        
        if not st.session_state.get("authentication_status"):
            st.write("---")
            with st.expander("새 계정 만들기"):
                with st.form("reg_form"):
                    new_name = st.text_input("이름")
                    new_user = st.text_input("아이디")
                    new_pwd = st.text_input("비밀번호", type="password")
                    if st.form_submit_button("가입하기"):
                        if new_name and new_user and new_pwd:
                            if new_user == MASTER_ACCOUNT_USERNAME:
                                st.error(f"'{MASTER_ACCOUNT_USERNAME}'은(는) 관리자용으로 예약된 아이디입니다. 다른 아이디를 사용해주세요.")
                                return
                            hashed_pwd = bcrypt.hashpw(new_pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                            success, msg = add_new_user(new_user, new_name, hashed_pwd)
                            if success: st.success("가입 완료! 로그인해주세요.")
                            else: st.error(msg)
                        else: st.error("모든 정보를 입력해주세요.")

if __name__ == "__main__":
    main()