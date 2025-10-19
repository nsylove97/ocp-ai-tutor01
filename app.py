# app.py
"""
Oracle OCP AI 튜터 메인 애플리케이션 파일
Streamlit을 사용하여 UI를 구성하고, 앱의 전체적인 흐름을 제어합니다.
"""
import streamlit as st
import random
import json
import os

# --- 3rd Party Libraries ---
from streamlit_quill import st_quill

# --- Custom Modules ---
from gemini_handler import generate_explanation, generate_modified_question
from db_utils import (
    setup_database_tables, load_original_questions_from_json,
    get_all_question_ids, get_question_by_id,
    add_new_original_question, update_original_question,
    get_wrong_answers, delete_wrong_answer,
    get_all_modified_questions, save_modified_question,
    delete_modified_question, clear_all_modified_questions,
    get_stats, get_top_5_missed,
)
from ui_components import display_question, display_results

# --- Constants ---
MEDIA_DIR = "media"

# --- Helper Functions ---

@st.cache_data
def get_ai_explanation(_q_id, _q_type):
    """
    문제 ID와 타입을 기반으로 AI 해설을 가져옵니다.
    Streamlit의 캐싱 기능을 사용하여 API 중복 호출을 방지합니다.

    Args:
        _q_id (int): 문제 ID.
        _q_type (str): 문제 타입 ('original' 또는 'modified').

    Returns:
        dict: AI가 생성한 해설 데이터 또는 에러 메시지.
    """
    question_data = get_question_by_id(_q_id, _q_type)
    if question_data:
        return generate_explanation(question_data)
    return {"error": f"DB에서 문제(ID: {_q_id}, Type: {_q_type})를 찾을 수 없습니다."}

def initialize_session_state():
    """
    앱의 세션 상태 변수를 초기화합니다.
    페이지가 재실행되어도 유지되어야 하는 값들을 관리합니다.
    """
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
    """'퀴즈 풀기' 메뉴의 메인 화면을 렌더링합니다."""
    st.header("📝 퀴즈 설정")
    quiz_mode = st.radio("퀴즈 모드를 선택하세요:", ("랜덤 퀴즈", "ID로 문제 풀기"), key="quiz_mode_selector", horizontal=True)

    if quiz_mode == "랜덤 퀴즈":
        num_questions = st.slider("풀고 싶은 문제 수를 선택하세요:", 1, 50, 10, key="num_questions_slider")
        quiz_type = st.radio("어떤 문제를 풀어볼까요?", ('기존 문제', '✨ AI 변형 문제'), key="quiz_type_selector")
        if st.button("랜덤 퀴즈 시작하기", type="primary"):
            start_quiz_session(quiz_mode, quiz_type=quiz_type, num_questions=num_questions)
    
    else: # "ID로 문제 풀기"
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
    """퀴즈가 진행되는 화면을 렌더링합니다."""
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


def render_notes_page():
    """'오답 노트' 화면을 렌더링합니다."""
    st.header("📒 오답 노트")
    wrong_answers = get_wrong_answers()

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
                        if "error" in explanation:
                            st.error(explanation["error"])
                        else:
                            st.info(f"**💡 쉬운 비유:**\n\n{explanation.get('analogy', 'N/A')}")
                            st.info(f"**🖼️ 텍스트 시각화:**\n\n```\n{explanation.get('visualization', 'N/A')}\n```")
                            st.info(f"**🔑 핵심 개념:**\n\n{explanation.get('core_concepts', 'N/A')}")


def render_results_page():
    """'퀴즈 결과' 화면을 렌더링합니다."""
    display_results(get_ai_explanation)
    if st.button("새 퀴즈 시작하기"):
        st.session_state.current_view = 'home'
        st.rerun()


def render_management_page():
    """'설정 및 관리' 화면을 렌더링합니다."""
    st.header("⚙️ 설정 및 관리")
    tabs = ["원본 문제 데이터", "문제 추가", "문제 편집", "오답 노트 관리", "AI 변형 문제 관리"]
    tab1, tab2, tab3, tab4, tab5 = st.tabs(tabs)

    with tab1:
        st.subheader("📚 원본 문제 데이터")
        st.info("배포된 환경에서 처음 사용하거나, 원본 문제를 초기화할 때 사용하세요.")
        num_questions = len(get_all_question_ids('original'))
        st.metric("현재 저장된 원본 문제 수", f"{num_questions} 개")
        if st.button("JSON에서 원본 문제 불러오기", type="primary"):
            with st.spinner("데이터베이스를 설정하는 중입니다..."):
                count, error = load_original_questions_from_json()
                if error:
                    st.error(f"문제 로딩 실패: {error}")
                else:
                    st.toast(f"성공적으로 {count}개의 문제를 불러왔습니다!")
                    st.rerun()

    with tab2:
        st.subheader("➕ 새로운 문제 추가")
        with st.form(key="add_form"):
            new_question_html = st_quill(placeholder="질문 내용을 입력하세요...", html=True, key="quill_add")
            uploaded_file = st.file_uploader("이미지/동영상 첨부", type=['png', 'jpg', 'jpeg', 'mp4'], key="uploader_add")
            st.number_input("선택지 개수:", min_value=2, max_value=10, key="new_option_count")
            
            new_options = {}
            for i in range(st.session_state.new_option_count):
                letter = chr(ord('A') + i)
                new_options[letter] = st.text_input(f"선택지 {letter}:", key=f"new_option_{letter}")
            
            valid_options = [k for k, v in new_options.items() if v.strip()]
            new_answer = st.multiselect("정답 선택:", options=valid_options)
            
            if st.form_submit_button("✅ 새 문제 추가하기"):
                if not new_question_html.strip() or new_question_html == '<p><br></p>':
                    st.error("질문 내용을 입력해야 합니다.")
                else:
                    media_url, media_type = None, None
                    if uploaded_file:
                        file_path = os.path.join(MEDIA_DIR, uploaded_file.name)
                        with open(file_path, "wb") as f: f.write(uploaded_file.getbuffer())
                        media_url = file_path
                        media_type = 'image' if uploaded_file.type.startswith('image') else 'video'
                    
                    final_options = {k: v for k, v in new_options.items() if k in valid_options}
                    new_id = add_new_original_question(new_question_html, final_options, new_answer, media_url, media_type)
                    st.toast(f"성공! 새 문제(ID: {new_id})가 추가되었습니다.", icon="🎉")
                    st.balloons()

    with tab3:
        st.subheader("✏️ 문제 편집")
        all_ids = get_all_question_ids('original')
        if not all_ids:
            st.info("편집할 원본 문제가 없습니다.")
        else:
            def change_id(amount):
                try:
                    current_index = all_ids.index(st.session_state.current_edit_id)
                    new_index = (current_index + amount) % len(all_ids) # 순환 구조
                    st.session_state.current_edit_id = all_ids[new_index]
                except ValueError:
                    st.session_state.current_edit_id = all_ids[0]

            col1, col2, col3 = st.columns([1, 2, 1])
            with col1: st.button("◀️ 이전", on_click=change_id, args=(-1,), use_container_width=True)
            with col2: st.selectbox("편집할 문제 ID 선택", options=all_ids, key="current_edit_id", label_visibility="collapsed")
            with col3: st.button("다음 ▶️", on_click=change_id, args=(1,), use_container_width=True)

            edit_id = st.session_state.current_edit_id
            question_to_edit = get_question_by_id(edit_id, 'original')
            if question_to_edit:
                with st.form(key=f"edit_form_{edit_id}"):
                    st.markdown(f"**ID {edit_id} 문제 수정:**")
                    current_options = json.loads(question_to_edit['options'])
                    current_answer = json.loads(question_to_edit['answer'])
                    
                    edited_question_html = st_quill(value=question_to_edit['question'] or "", html=True, key=f"quill_{edit_id}")
                    
                    if question_to_edit.get('media_url'):
                        st.write("**현재 첨부 파일:**", os.path.basename(question_to_edit['media_url']))
                    edited_file = st.file_uploader("새 파일로 교체", key=f"uploader_{edit_id}")
                    
                    edited_options = {k: st.text_input(f"선택지 {k}:", value=v, key=f"opt_{k}_{edit_id}") for k, v in current_options.items()}
                    edited_answer = st.multiselect("정답:", options=list(edited_options.keys()), default=current_answer, key=f"ans_{edit_id}")
                    
                    if st.form_submit_button("변경사항 저장"):
                        media_url, media_type = question_to_edit.get('media_url'), question_to_edit.get('media_type')
                        if edited_file:
                            file_path = os.path.join(MEDIA_DIR, edited_file.name)
                            with open(file_path, "wb") as f: f.write(edited_file.getbuffer())
                            media_url = file_path
                            media_type = 'image' if edited_file.type.startswith('image') else 'video'

                        update_original_question(edit_id, edited_question_html, edited_options, edited_answer, media_url, media_type)
                        st.toast(f"ID {edit_id} 문제가 업데이트되었습니다!", icon="✅")
                        st.cache_data.clear()
                        st.rerun()

    with tab4:
        st.subheader("📒 오답 노트 관리")
        wrong_answers = get_wrong_answers()
        if not wrong_answers:
            st.info("관리할 오답 노트가 없습니다.")
        else:
            st.warning(f"총 {len(wrong_answers)}개의 오답 기록이 있습니다.")
            for q_info in wrong_answers:
                question = get_question_by_id(q_info['question_id'], q_info['question_type'])
                if question:
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        q_text = question['question'].replace('<p>', '').replace('</p>', '')
                        st.text(f"ID {question['id']} ({q_info['question_type']}): {q_text[:70]}...")
                    with col2:
                        if st.button("삭제", key=f"del_wrong_{q_info['question_id']}_{q_info['question_type']}", type="secondary"):
                            delete_wrong_answer(q_info['question_id'], q_info['question_type'])
                            st.toast(f"ID {question['id']} 오답 기록이 삭제되었습니다.", icon="🗑️")
                            st.rerun()
                            
    with tab5:
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
                col1, col2 = st.columns([4, 1])
                with col1:
                    q_text = mq['question'].replace('<p>', '').replace('</p>', '')
                    st.text(f"ID {mq['id']}: {q_text[:80]}...")
                with col2:
                    if st.button("삭제", key=f"del_mod_{mq['id']}", type="secondary"):
                        delete_modified_question(mq['id'])
                        st.toast(f"ID {mq['id']} 변형 문제가 삭제되었습니다.", icon="🗑️")
                        st.rerun()

def render_analytics_page():
    """'학습 통계' 화면을 렌더링합니다."""
    st.header("📈 학습 통계")
    total, correct, accuracy = get_stats()
    col1, col2, col3 = st.columns(3)
    col1.metric("총 풀이 문제 수", f"{total} 개")
    col2.metric("총 정답 수", f"{correct} 개")
    col3.metric("전체 정답률", f"{accuracy:.2f} %")
    st.write("---")
    st.subheader("가장 많이 틀린 문제 Top 5 (원본 문제 기준)")
    df_missed = get_top_5_missed()
    if df_missed.empty:
        st.info("틀린 문제 기록이 충분하지 않습니다.")
    else:
        for _, row in df_missed.iterrows():
            with st.container(border=True):
                st.write(f"**오답 횟수: {row['wrong_count']}회**")
                st.caption(f"문제 ID: {row['id']}")
                st.markdown(row['question'], unsafe_allow_html=True)

# --- Main App Logic ---
def main():
    """메인 실행 함수"""
    st.set_page_config(page_title="Oracle OCP AI 튜터", layout="wide", initial_sidebar_state="expanded")
    
    # 앱 시작 시 DB 테이블 구조 확인 및 생성
    if 'db_setup_done' not in st.session_state:
        setup_database_tables()
        st.session_state.db_setup_done = True
    
    st.title("🚀 Oracle OCP AI 튜터")
    initialize_session_state()

    # --- Sidebar Navigation ---
    st.sidebar.title("메뉴")
    view_options = {
        "home": "📝 퀴즈 풀기",
        "notes": "📒 오답 노트",
        "analytics": "📈 학습 통계",
        "manage": "⚙️ 설정 및 관리"
    }
    for view, label in view_options.items():
        if st.sidebar.button(label, use_container_width=True, type="primary" if st.session_state.current_view == view else "secondary"):
            st.session_state.current_view = view
            if view == 'home': # 퀴즈 풀기 메뉴를 누르면 퀴즈 상태 초기화
                st.session_state.questions_to_solve = []
                st.session_state.user_answers = {}
                st.session_state.current_question_index = 0
            st.rerun()

    # --- App Management in Sidebar ---
    st.sidebar.write("---")
    st.sidebar.subheader("앱 관리")
    if st.sidebar.button("현재 학습 초기화", use_container_width=True):
        keys_to_keep = ['current_view', 'db_setup_done']
        for key in list(st.session_state.keys()):
            if key not in keys_to_keep:
                del st.session_state[key]
        st.toast("현재 학습 상태가 초기화되었습니다.", icon="🔄")
        st.rerun()

    with st.sidebar.expander("⚠️ 전체 데이터 초기화"):
        st.warning("모든 오답 기록과 AI 생성 문제를 영구적으로 삭제합니다.")
        if st.button("모든 기록 삭제", type="primary", use_container_width=True):
            conn = get_db_connection()
            conn.execute("DELETE FROM user_answers")
            conn.commit()
            conn.close()
            clear_all_modified_questions()
            st.toast("모든 학습 기록이 영구적으로 삭제되었습니다.", icon="💥")
            st.session_state.clear()
            st.rerun()

    # --- Main Content Area ---
    view_map = {
        "home": render_home_page,
        "quiz": render_quiz_page,
        "results": render_results_page,
        "notes": render_notes_page,
        "manage": render_management_page,
        "analytics": render_analytics_page,
    }
    render_func = view_map.get(st.session_state.current_view)
    if render_func:
        render_func()
    else:
        st.error("알 수 없는 페이지입니다. 홈으로 돌아갑니다.")
        st.session_state.current_view = 'home'
        st.rerun()

if __name__ == "__main__":
    main()