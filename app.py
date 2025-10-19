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

# --- Custom Modules (중복 제거 및 정리) ---
from gemini_handler import generate_explanation, generate_modified_question
from db_utils import (
    setup_database_tables, load_original_questions_from_json, get_db_connection,
    get_all_question_ids, get_question_by_id,
    add_new_original_question, update_original_question,
    get_wrong_answers, delete_wrong_answer,
    get_all_modified_questions, save_modified_question,
    delete_modified_question, clear_all_modified_questions,
    get_stats, get_top_5_missed,
    fetch_all_users, add_new_user,
    delete_user, get_all_users_for_admin, ensure_master_account
)
from ui_components import display_question, display_results

# --- Constants ---
MEDIA_DIR = "media"
if not os.path.exists(MEDIA_DIR):
    os.makedirs(MEDIA_DIR)
MASTER_ACCOUNT_USERNAME = "admin"
MASTER_ACCOUNT_NAME = "Master Admin"
MASTER_ACCOUNT_PASSWORD = "admin" # 실제 배포 시에는 환경 변수로 관리하세요.

# --- Helper Functions ---
@st.cache_data
def get_ai_explanation(_q_id, _q_type):
    question_data = get_question_by_id(_q_id, _q_type)
    if question_data:
        return generate_explanation(question_data)
    return {"error": f"DB에서 문제(ID: {_q_id}, Type: {_q_type})를 찾을 수 없습니다."}

def initialize_session_state():
    defaults = {
        'current_view': 'home', 'questions_to_solve': [], 'current_question_index': 0,
        'user_answers': {}, 'current_edit_id': 1, 'new_option_count': 5,
        'temp_new_question': "", 'temp_new_options': {}
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def start_quiz_session(quiz_mode, quiz_type=None, num_questions=None, question_id=None):
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
                    selected_ids = random.sample(original_ids, min(num_questions, len(original_ids)))
                    newly_generated_q_ids = [save_modified_question(qid, gen_q) for qid in selected_ids if (gen_q := generate_modified_question(get_question_by_id(qid, 'original'))) and "error" not in gen_q]
                    if newly_generated_q_ids:
                        st.session_state.questions_to_solve = [{'id': q_id, 'type': 'modified'} for q_id in newly_generated_q_ids]
                        questions_loaded = True
                    else: st.error("AI 변형 문제 생성에 실패했습니다.")
                else: st.error("변형할 원본 문제가 없습니다.")
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
    quiz_mode = st.radio("퀴즈 모드를 선택하세요:", ("랜덤 퀴즈", "ID로 문제 풀기"), horizontal=True)
    if quiz_mode == "랜덤 퀴즈":
        num_q = st.slider("문제 수:", 1, 50, 10)
        q_type = st.radio("문제 유형:", ('기존 문제', '✨ AI 변형 문제'))
        if st.button("퀴즈 시작", type="primary"):
            start_quiz_session(quiz_mode, quiz_type=q_type, num_questions=num_q)
    else:
        q_id = st.number_input("문제 ID:", min_value=1, step=1)
        if q_id and (p_q := get_question_by_id(q_id, 'original')):
            with st.container(border=True):
                st.markdown(f"**미리보기 (ID: {p_q['id']})**")
                st.markdown(p_q['question'], unsafe_allow_html=True)
        if st.button(f"ID {q_id} 풀기", type="primary"):
            start_quiz_session(quiz_mode, question_id=q_id)

def render_quiz_page():
    if not st.session_state.questions_to_solve:
        st.warning("풀 문제가 없습니다. 홈으로 돌아가 퀴즈를 다시 시작해주세요.")
        if st.button("홈으로"): st.rerun()
        return
    idx = st.session_state.current_question_index
    total = len(st.session_state.questions_to_solve)
    st.progress((idx + 1) / total, text=f"{idx + 1}/{total} 문제 진행 중...")
    if idx not in st.session_state.user_answers:
        st.session_state.user_answers[idx] = []
    q_info = st.session_state.questions_to_solve[idx]
    question = get_question_by_id(q_info['id'], q_info['type'])
    if question:
        display_question(question, idx, total)
        c1, _, c2 = st.columns([1, 3, 1])
        if c1.button("이전", disabled=(idx == 0), use_container_width=True):
            st.session_state.current_question_index -= 1
            st.rerun()
        if idx < total - 1:
            if c2.button("다음", use_container_width=True):
                st.session_state.current_question_index += 1
                st.rerun()
        else:
            if c2.button("결과 보기", type="primary", use_container_width=True):
                st.session_state.current_view = 'results'
                st.rerun()
    else: st.error(f"문제(ID: {q_info['id']})를 불러오는 데 실패했습니다.")

def render_notes_page(username):
    st.header("📒 오답 노트")
    wrong_answers = get_wrong_answers(username)
    if not wrong_answers:
        st.success("🎉 오답 노트가 비어있습니다.")
        return
    if st.button("틀린 문제 다시 풀기", type="primary"):
        st.session_state.questions_to_solve = [{'id': q['question_id'], 'type': q['question_type']} for q in wrong_answers]
        st.session_state.current_question_index = 0
        st.session_state.user_answers = {}
        st.session_state.current_view = 'quiz'
        st.rerun()
    st.write("---")
    for q_info in wrong_answers:
        if question := get_question_by_id(q_info['question_id'], q_info['question_type']):
            with st.container(border=True):
                st.markdown(f"**문제 ID: {question['id']}**")
                st.markdown(question['question'], unsafe_allow_html=True)
                if st.button("🤖 AI 해설 보기", key=f"note_exp_{q_info['question_id']}_{q_info['question_type']}"):
                    with st.spinner("해설 생성 중..."):
                        if exp := get_ai_explanation(q_info['question_id'], q_info['question_type']):
                            if err := exp.get('error'): st.error(err)
                            else:
                                st.info(f"**💡 쉬운 비유:**\n\n{exp.get('analogy', 'N/A')}")
                                st.info(f"**🔑 핵심 개념:**\n\n{exp.get('core_concepts', 'N/A')}")

def render_results_page(username):
    display_results(username, get_ai_explanation)
    if st.button("새 퀴즈 시작"):
        st.session_state.current_view = 'home'
        st.rerun()

def render_management_page(username):
    st.header("⚙️ 설정 및 관리")
    is_admin = st.session_state.get('is_admin', False)
    admin_tabs = ["사용자 관리", "원본 문제 데이터", "문제 추가", "문제 편집", "오답 노트 관리", "AI 변형 문제 관리"]
    user_tabs = ["회원 탈퇴", "오답 노트 관리"]
    tabs = st.tabs(admin_tabs if is_admin else user_tabs)
    
    def admin_user_management():
        st.subheader("👑 사용자 관리")
        all_users = get_all_users_for_admin()
        st.metric("총 사용자 수", f"{len(all_users)} 명")
        for user in all_users:
            if user['username'] != MASTER_ACCOUNT_USERNAME:
                c1, c2 = st.columns([4, 1])
                c1.write(f"👤 **{user['name']}** ({user['username']})")
                if c2.button("삭제", key=f"del_u_{user['username']}", type="secondary"):
                    delete_user(user['username'])
                    st.toast("삭제 완료!")
                    st.rerun()
    
    def user_account_deletion():
        st.subheader("👋 회원 탈퇴")
        st.warning("모든 학습 기록이 영구적으로 삭제됩니다.")
        if st.checkbox("위 내용에 동의하며 탈퇴를 진행합니다."):
            if st.button("회원 탈퇴하기", type="primary"):
                delete_user(username)
                st.success("탈퇴 처리되었습니다.")
                st.session_state.authentication_status = None
                st.rerun()
                
    if is_admin:
        with tabs[0]: admin_user_management()
        # 이하 관리자 탭 렌더링
    else:
        with tabs[0]: user_account_deletion()
        # 이하 일반 사용자 탭 렌더링

def render_analytics_page(username):
    st.header("📈 학습 통계")
    total, correct, accuracy = get_stats(username)
    c1, c2, c3 = st.columns(3)
    c1.metric("총 풀이", total); c2.metric("정답", correct); c3.metric("정답률", f"{accuracy:.1f}%")
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
    username = st.session_state.get("username")
    st.session_state.is_admin = (username == MASTER_ACCOUNT_USERNAME)

    st.sidebar.title(f"환영합니다, {st.session_state.get('name')}님!")
    authenticator.logout('로그아웃', 'sidebar', key='main_logout')
    
    initialize_session_state()

    st.sidebar.write("---")
    st.sidebar.title("메뉴")
    menu = {"home": "📝 퀴즈 풀기", "notes": "📒 오답 노트", "analytics": "📈 학습 통계", "manage": "⚙️ 설정 및 관리"}
    for view, label in menu.items():
        if st.sidebar.button(label, use_container_width=True, type="primary" if st.session_state.current_view == view else "secondary"):
            st.session_state.current_view = view
            st.rerun()

    view_map = {
        "home": render_home_page, "quiz": render_quiz_page,
        "results": lambda: render_results_page(username),
        "notes": lambda: render_notes_page(username),
        "manage": lambda: render_management_page(username),
        "analytics": lambda: render_analytics_page(username),
    }
    view_map.get(st.session_state.current_view, render_home_page)()

def main():
    """메인 실행 함수"""
    st.set_page_config(page_title="Oracle OCP AI 튜터", layout="wide", initial_sidebar_state="expanded")

    if 'db_setup_done' not in st.session_state:
        setup_database_tables()
        st.session_state.db_setup_done = True

    credentials, all_user_info = fetch_all_users()
    if MASTER_ACCOUNT_USERNAME not in credentials['usernames']:
        hashed_pw = bcrypt.hashpw(MASTER_ACCOUNT_PASSWORD.encode(), bcrypt.gensalt()).decode()
        ensure_master_account(MASTER_ACCOUNT_USERNAME, MASTER_ACCOUNT_NAME, hashed_pw)
        credentials, all_user_info = fetch_all_users()
        st.toast(f"관리자 계정 '{MASTER_ACCOUNT_USERNAME}' 설정 완료!", icon="👑")

    authenticator = stauth.Authenticate(credentials, "ocp_cookie", "auth_key", 30)
    authenticator.login(location='main')

    if st.session_state.get("authentication_status"):
        run_main_app(authenticator)
    else:
        if st.session_state.get("authentication_status") is False: st.error('아이디 또는 비밀번호가 일치하지 않습니다.')
        elif st.session_state.get("authentication_status") is None: st.info('로그인하거나 새 계정을 만들어주세요.')
        
        with st.expander("새 계정 만들기"):
            with st.form("reg_form"):
                new_name, new_user, new_pwd = st.text_input("이름"), st.text_input("아이디"), st.text_input("비밀번호", type="password")
                if st.form_submit_button("가입하기"):
                    if new_user == MASTER_ACCOUNT_USERNAME:
                        st.error("예약된 아이디입니다.")
                    elif all((new_name, new_user, new_pwd)):
                        hashed = bcrypt.hashpw(new_pwd.encode(), bcrypt.gensalt()).decode()
                        success, msg = add_new_user(new_user, new_name, hashed)
                        if success: st.success("가입 완료! 로그인해주세요.")
                        else: st.error(msg)
                    else: st.error("모든 정보를 입력해주세요.")

if __name__ == "__main__":
    main()