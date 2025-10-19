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
from dotenv import load_dotenv

# --- 3rd Party Libraries ---
from streamlit_quill import st_quill
from streamlit_modal import Modal

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
    fetch_all_users, add_new_user,
    delete_user, get_all_users_for_admin, ensure_master_account,
    get_question_ids_by_difficulty
)
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
        if q := get_question_by_id(q_info['question_id'], q_info['question_type']):
            with st.container(border=True):
                st.markdown(f"**문제 ID: {q['id']}** ({q_info['question_type']})")
                st.markdown(q['question'], unsafe_allow_html=True)
                if st.button("🤖 AI 해설", key=f"note_exp_{q['id']}_{q_info['question_type']}"):
                    with st.spinner("해설 생성 중..."):
                        if exp := get_ai_explanation(q['id'], q_info['question_type']):
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
        st.info("JSON 파일의 모든 문제를 불러와 AI가 자동으로 난이도를 분석하여 저장합니다. (시간이 다소 소요될 수 있습니다)")
        
        num_q = len(get_all_question_ids('original'))
        st.metric("현재 저장된 문제 수", f"{num_q} 개")

        if st.button("AI 자동 난이도 부여 및 문제 불러오기", type="primary"):
            progress_bar = st.progress(0, text="AI 난이도 분석 시작...")
            
            try:
                progress_generator = load_original_questions_from_json()
                for progress in progress_generator:
                    progress_bar.progress(progress, text=f"AI 난이도 분석 중... ({int(progress*100)}%)")
                else: # 루프가 break 없이 완료되면 실행
                    st.toast("모든 문제에 대한 AI 난이도 분석 및 저장이 완료되었습니다!", icon="✅")
            except Exception as e:
                st.error(f"데이터 로딩 중 오류가 발생했습니다: {e}")
            finally:
                progress_bar.empty() # 진행률 바 숨기기
                st.rerun()

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

    with tabs[4]: #오답 노트 관리
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

    with tabs[5]: # AI 변형 문제 관리
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

    # --- 4. 인증 상태에 따라 화면 분기 ---
    if st.session_state.get("authentication_status"):
        # --- 4a. 로그인 성공 시 ---
        run_main_app(authenticator, all_user_info)

    else:
        # --- 4b. 로그인하지 않은 경우 ---
        st.markdown("""
            <style>
                /* 로그인 폼 컨테이너의 최대 너비를 설정 */
                .login-container {
                    max-width: 450px;
                }
            </style>
        """, unsafe_allow_html=True)

        with st.container():
            st.markdown('<div class="login-container">', unsafe_allow_html=True)
            authenticator.login(location='main')
            st.markdown('</div>', unsafe_allow_html=True)

        if st.session_state.get("authentication_status") is False:
            st.error('아이디 또는 비밀번호가 일치하지 않습니다.')
        elif st.session_state.get("authentication_status") is None:
            st.info('로그인하거나 아래에서 새 계정을 만들어주세요.')
        
        # 회원가입 폼 렌더링
        st.write("---")
        with st.expander("새 계정 만들기"):
            with st.form("reg_form"):
                new_name = st.text_input("이름")
                new_user = st.text_input("아이디")
                new_pwd = st.text_input("비밀번호", type="password")
                if st.form_submit_button("가입하기"):
                    if new_user == MASTER_ACCOUNT_USERNAME:
                        st.error("예약된 아이디입니다.")
                    elif all((new_name, new_user, new_pwd)):
                        hashed = bcrypt.hashpw(new_pwd.encode(), bcrypt.gensalt()).decode()
                        success, msg = add_new_user(new_user, new_name, hashed)
                        if success:
                            st.success("가입 완료! 로그인해주세요.")
                        else:
                            st.error(msg)
                    else:
                        st.error("모든 정보를 입력해주세요.")

if __name__ == "__main__":
    main()