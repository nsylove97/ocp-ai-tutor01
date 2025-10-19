# app.py (수정 완료 버전)
import streamlit as st
import random
import json
import pandas as pd
import os
from streamlit_quill import st_quill
from gemini_handler import generate_explanation, generate_modified_question
from db_utils import (
    get_all_question_ids, get_question_by_id, get_wrong_answers,
    save_modified_question, get_all_modified_questions,
    delete_wrong_answer, delete_modified_question, clear_all_modified_questions,
    get_stats, get_top_5_missed,
    setup_database_tables, load_original_questions_from_json,
    update_original_question, add_new_original_question
)
from ui_components import display_question, display_results

# --- 미디어 파일 저장 경로 설정 ---
MEDIA_DIR = "media"
if not os.path.exists(MEDIA_DIR):
    os.makedirs(MEDIA_DIR)

# --- AI 해설 함수에 캐싱 적용 ---
@st.cache_data
def get_ai_explanation(_q_id, _q_type):
    question_data = get_question_by_id(_q_id, _q_type)
    if question_data:
        return generate_explanation(question_data)
    else:
        return {"error": f"데이터베이스에서 해당 문제(ID: {_q_id}, Type: {_q_type})를 찾을 수 없습니다."}

# --- 상태 관리 함수 ---
def initialize_session_state():
    if 'current_view' not in st.session_state:
        st.session_state.current_view = 'home'
    if 'questions_to_solve' not in st.session_state:
        st.session_state.questions_to_solve = []
    if 'current_question_index' not in st.session_state:
        st.session_state.current_question_index = 0
    if 'user_answers' not in st.session_state:
        st.session_state.user_answers = {}

# --- 페이지 렌더링 함수 ---

def render_home_page():
    st.header("📝 퀴즈 설정")
    quiz_mode = st.radio("퀴즈 모드를 선택하세요:", ("랜덤 퀴즈", "ID로 문제 풀기"), key="quiz_mode_selector", horizontal=True)
    start_quiz_button = False

    if quiz_mode == "랜덤 퀴즈":
        num_questions = st.slider("풀고 싶은 문제 수를 선택하세요:", 1, 50, 10, key="num_questions_slider")
        quiz_type = st.radio("어떤 문제를 풀어볼까요?", ('기존 문제', '✨ AI 변형 문제'), key="quiz_type_selector")
        if st.button("랜덤 퀴즈 시작하기", type="primary"):
            start_quiz_button = True
    else: # "ID로 문제 풀기"
        question_id = st.number_input("풀고 싶은 원본 문제의 ID를 입력하세요:", min_value=1, step=1, key="target_question_id")
        if question_id:
            preview_question = get_question_by_id(question_id, 'original')
            if preview_question:
                with st.container(border=True):
                    st.markdown("**미리보기:**")
                    st.markdown(preview_question['question'], unsafe_allow_html=True)
                    if preview_question.get('media_url'):
                        if preview_question.get('media_type') == 'image':
                            st.image(preview_question['media_url'])
                        else:
                            st.video(preview_question['media_url'])
            else:
                st.warning(f"ID {question_id}에 해당하는 문제를 찾을 수 없습니다.")
        if st.button(f"ID {question_id} 문제 풀기", type="primary"):
            start_quiz_button = True

    if start_quiz_button:
        st.session_state.questions_to_solve = []
        st.session_state.user_answers = {}
        st.session_state.current_question_index = 0
        should_rerun = False
        
        if quiz_mode == "랜덤 퀴즈":
            if quiz_type == '기존 문제':
                all_ids = get_all_question_ids('original')
                if all_ids:
                    selected_ids = random.sample(all_ids, min(num_questions, len(all_ids)))
                    st.session_state.questions_to_solve = [{'id': q_id, 'type': 'original'} for q_id in selected_ids]
                    st.session_state.current_view = 'quiz'
                    should_rerun = True
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
                            modified_q_data = generate_modified_question(original_question)
                            if modified_q_data and "error" not in modified_q_data:
                                new_id = save_modified_question(original_id, modified_q_data)
                                newly_generated_q_ids.append(new_id)
                        if newly_generated_q_ids:
                            st.session_state.questions_to_solve = [{'id': q_id, 'type': 'modified'} for q_id in newly_generated_q_ids]
                            st.session_state.current_view = 'quiz'
                            should_rerun = True
                        else:
                            st.error("AI 변형 문제 생성에 실패했습니다.")
                    else:
                        st.error("변형할 원본 문제가 없습니다.")
        else: # "ID로 문제 풀기"
            target_question = get_question_by_id(question_id, 'original')
            if target_question:
                st.session_state.questions_to_solve = [{'id': question_id, 'type': 'original'}]
                st.session_state.current_view = 'quiz'
                should_rerun = True
            else:
                st.error(f"ID {question_id}에 해당하는 원본 문제를 찾을 수 없습니다.")

        if should_rerun:
            st.rerun()

def render_quiz_page():
    if not st.session_state.questions_to_solve:
        st.warning("풀 문제가 없습니다. 홈 화면으로 돌아가 퀴즈를 다시 시작해주세요.")
        if st.button("홈으로 돌아가기"):
            st.session_state.current_view = 'home'
            st.rerun()
        return

    idx = st.session_state.current_question_index
    total_questions = len(st.session_state.questions_to_solve)

    progress_percent = (idx + 1) / total_questions
    st.progress(progress_percent, text=f"{idx + 1}/{total_questions} 문제 진행 중...")

    if idx not in st.session_state.user_answers:
        st.session_state.user_answers[idx] = []

    q_info = st.session_state.questions_to_solve[idx]
    question = get_question_by_id(q_info['id'], q_info['type'])

    if question:
        display_question(question, idx, total_questions)
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            if st.button("이전", disabled=(idx == 0)):
                st.session_state.current_question_index -= 1
                st.rerun()
        with col3:
            if idx < total_questions - 1:
                if st.button("다음"):
                    st.session_state.current_question_index += 1
                    st.rerun()
            else:
                if st.button("결과 보기", type="primary"):
                    st.session_state.current_view = 'results'
                    st.rerun()
    else:
        st.error(f"문제(ID: {q_info['id']}, Type: {q_info['type']})를 불러오는 데 실패했습니다.")

def render_notes_page():
    st.header("📒 오답 노트")
    wrong_answers = get_wrong_answers()

    if not wrong_answers:
        st.success("🎉 축하합니다! 틀린 문제가 없습니다.")
    else:
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
                                st.info(f"**💡 쉬운 비유**\n\n{explanation.get('analogy', 'N/A')}")
                                st.info(f"**🖼️ 텍스트 시각화**\n\n```\n{explanation.get('visualization', 'N/A')}\n```")
                                st.info(f"**🔑 핵심 개념 정리**\n\n{explanation.get('core_concepts', 'N/A')}")

def render_results_page():
    display_results(get_ai_explanation)
    if st.button("새 퀴즈 시작하기"):
        st.session_state.current_view = 'home'
        st.rerun()

def render_management_page():
    st.header("⚙️ 설정 및 관리")
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "원본 문제 데이터", "문제 추가 (원본)", "문제 편집 (원본)",
        "오답 노트 관리", "AI 변형 문제 관리"
    ])

    with tab1:
        st.subheader("📚 원본 문제 데이터 관리")
        st.info("배포된 환경에서 처음 앱을 사용하거나 원본 문제를 초기화하고 싶을 때 사용하세요.")
        num_original_questions = len(get_all_question_ids('original'))
        st.metric("현재 저장된 원본 문제 수", f"{num_original_questions} 개")
        if st.button("JSON 파일에서 원본 문제 불러오기", type="primary"):
            with st.spinner("`questions_final.json` 파일을 읽어 데이터베이스를 설정하는 중입니다..."):
                setup_database_tables()
                count, error = load_original_questions_from_json()
                if error:
                    st.error(f"문제 로딩 실패: {error}")
                else:
                    st.toast(f"성공적으로 {count}개의 원본 문제를 데이터베이스에 불러왔습니다!")
                    st.rerun()

    with tab2:
        st.subheader("➕ 새로운 원본 문제 추가")
        st.info("새로운 OCP 문제를 직접 추가하여 나만의 문제 은행을 만드세요.")
    
        # Quill 에디터 (HTML 형식으로 내용 반환)
        # session_state에 임시로 저장하여 form 제출 시 값을 가져올 수 있도록 함
        if 'temp_new_question' not in st.session_state:
            st.session_state.temp_new_question = ""
        st.session_state.temp_new_question = st_quill(
            value=st.session_state.temp_new_question,
            placeholder="여기에 질문 내용을 입력하세요...", 
            html=True, 
            key="quill_add"
        )

        # 미디어 파일 업로드 (form 밖)
        uploaded_file = st.file_uploader("이미지 또는 동영상 첨부 (선택 사항)", type=['png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov'], key="uploader_add")
        
        st.write("---")
        st.subheader("선택지 및 정답 설정")

        # 선택지 개수 조절 (form 밖)
        if 'new_option_count' not in st.session_state:
            st.session_state.new_option_count = 5
        st.number_input(
            "선택지 개수:", 
            min_value=2, 
            max_value=10,
            key="new_option_count"
        )

        # 선택지 내용 입력 (form 밖)
        # 입력된 내용은 session_state에 임시 저장
        if 'temp_new_options' not in st.session_state:
            st.session_state.temp_new_options = {}

        for i in range(st.session_state.new_option_count):
            letter = chr(ord('A') + i)
            st.session_state.temp_new_options[letter] = st.text_input(
                f"선택지 {letter}:", 
                value=st.session_state.temp_new_options.get(letter, ""),
                key=f"temp_option_{letter}"
            )
        
        with st.form(key="add_form_submit"):
            st.markdown("**모든 내용을 입력했으면 아래 버튼을 눌러 추가하세요.**")
            
            # 정답 선택 (form 안)
            # session_state에 저장된 임시 선택지 값을 가져와서 사용
            valid_options = [letter for letter, text in st.session_state.temp_new_options.items() if text.strip()]
            new_answer = st.multiselect("정답 선택:", options=valid_options)
            
            submitted = st.form_submit_button("✅ 새 문제 추가하기")

            if submitted:
                # 제출 시, session_state에 저장된 임시 값들을 가져와 처리
                new_question_html = st.session_state.temp_new_question
                new_options = st.session_state.temp_new_options
                
                # 유효성 검사
                if not new_question_html or not new_question_html.strip() or new_question_html == '<p><br></p>':
                    st.error("질문 내용을 입력해야 합니다.")
                elif not valid_options:
                    st.error("선택지 내용을 하나 이상 입력해야 합니다.")
                elif not new_answer:
                    st.error("정답을 하나 이상 선택해야 합니다.")
                else:
                    # 미디어 파일 처리
                    # (uploaded_file은 form 밖에 있으므로, 이 시점에 값을 직접 사용할 수 있음)
                    media_url, media_type = None, None
                    if uploaded_file is not None:
                        file_path = os.path.join(MEDIA_DIR, uploaded_file.name)
                        with open(file_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                        media_url = file_path
                        media_type = 'image' if uploaded_file.type.startswith('image') else 'video'
                    
                    final_options = {key: value for key, value in new_options.items() if key in valid_options}
                    new_id = add_new_original_question(new_question_html, final_options, new_answer, media_url, media_type)
                    
                    # 성공 후 임시 상태 초기화
                    st.session_state.temp_new_question = ""
                    st.session_state.temp_new_options = {}
                    # uploaded_file은 직접 초기화 불가, 하지만 다음 rerun 시 초기화됨
                    
                    st.success(f"성공적으로 새로운 문제(ID: {new_id})를 추가했습니다!")
                    st.balloons()

    with tab3:
        st.subheader("✏️ 원본 문제 편집")
        all_ids = get_all_question_ids('original')
        if not all_ids:
            st.info("편집할 원본 문제가 없습니다.")
        else:
            min_id, max_id = min(all_ids), max(all_ids)
            if 'current_edit_id' not in st.session_state:
                st.session_state.current_edit_id = min_id
            def change_id(amount):
                try:
                    current_index = all_ids.index(st.session_state.current_edit_id)
                    new_index = current_index + amount
                    if 0 <= new_index < len(all_ids):
                        st.session_state.current_edit_id = all_ids[new_index]
                except ValueError:
                    st.session_state.current_edit_id = min_id
            col1, col2, col3 = st.columns([1, 2, 1])
            with col1:
                st.button("◀️ 이전 문제", on_click=change_id, args=(-1,), use_container_width=True)
            with col2:
                st.number_input("편집할 문제 ID", min_value=min_id, max_value=max_id, key="current_edit_id", label_visibility="collapsed")
            with col3:
                st.button("다음 문제 ▶️", on_click=change_id, args=(1,), use_container_width=True)
            st.write("---")
            edit_id = st.session_state.current_edit_id
            question_to_edit = get_question_by_id(edit_id, 'original')
            if question_to_edit:
                with st.form(key=f"edit_form_{edit_id}"):
                    st.markdown(f"**ID {edit_id} 문제 수정:**")
                    current_question_html = question_to_edit['question'] or ""
                    current_options = json.loads(question_to_edit['options'])
                    current_answer = json.loads(question_to_edit['answer'])
                    edited_question_html = st_quill(value=current_question_html, html=True, key=f"quill_edit_{edit_id}")
                    if question_to_edit.get('media_url'):
                        st.write("**현재 첨부된 미디어:**")
                        # (미디어 표시 로직)
                    edited_uploaded_file = st.file_uploader("새 미디어 파일로 교체", key=f"uploader_{edit_id}")
                    st.write("**선택지 및 정답 수정:**")
                    edited_options = {key: st.text_input(f"선택지 {key}:", value=value, key=f"option_{key}_{edit_id}") for key, value in current_options.items()}
                    edited_answer = st.multiselect("정답 선택:", options=list(edited_options.keys()), default=current_answer, key=f"answer_{edit_id}")
                    if st.form_submit_button("변경사항 저장"):
                        media_url, media_type = question_to_edit.get('media_url'), question_to_edit.get('media_type')
                        if edited_uploaded_file is not None:
                            # (파일 저장 로직)
                            pass
                        update_original_question(edit_id, edited_question_html, edited_options, edited_answer, media_url, media_type)
                        st.success(f"ID {edit_id} 문제가 업데이트되었습니다!")
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
                        st.text(f"ID {question['id']} ({q_info['question_type']}): {question['question'].replace('<p>', '').replace('</p>', '')[:70]}...")
                    with col2:
                        if st.button("삭제", key=f"del_wrong_{q_info['question_id']}_{q_info['question_type']}", type="secondary"):
                            delete_wrong_answer(q_info['question_id'], q_info['question_type'])
                            st.toast(f"ID {question['id']} 오답 기록이 삭제되었습니다.")
                            st.rerun()
    
    with tab5:
        st.subheader("✨ AI 변형 문제 관리")
        modified_questions = get_all_modified_questions()
        if not modified_questions:
            st.info("관리할 AI 변형 문제가 없습니다.")
        else:
            if st.button("모든 변형 문제 삭제", type="primary"):
                clear_all_modified_questions()
                st.toast("모든 AI 변형 문제가 삭제되었습니다.")
                st.rerun()
            for mq in modified_questions:
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.text(f"ID {mq['id']}: {mq['question'][:80]}...")
                with col2:
                    if st.button("삭제", key=f"del_mod_{mq['id']}", type="secondary"):
                        delete_modified_question(mq['id'])
                        st.toast(f"ID {mq['id']} 변형 문제가 삭제되었습니다.")
                        st.rerun()
def render_analytics_page():
    """학습 통계 대시보드 페이지 (차트 제거 버전)"""
    st.header("📈 학습 통계")
    
    # get_stats 함수는 db_utils.py에 이미 정의되어 있습니다.
    total, correct, accuracy = get_stats()

    col1, col2, col3 = st.columns(3)
    col1.metric("총 풀이 문제 수", f"{total} 개")
    col2.metric("총 정답 수", f"{correct} 개")
    col3.metric("전체 정답률", f"{accuracy:.2f} %")

    st.write("---")

    st.subheader("가장 많이 틀린 문제 Top 5 (원본 문제 기준)")
    # get_top_5_missed 함수는 db_utils.py에 이미 정의되어 있습니다.
    df_missed = get_top_5_missed()

    if df_missed.empty:
        st.info("틀린 문제 기록이 충분하지 않습니다.")
    else:
        # 데이터프레임을 표 형태로 깔끔하게 보여줍니다.
        for index, row in df_missed.iterrows():
            with st.container(border=True):
                st.write(f"**오답 횟수: {row['wrong_count']}회**")
                # 원본 문제 번호(ID)를 함께 표시합니다.
                st.caption(f"문제 ID: {row['id']}")
                st.markdown(row['question'], unsafe_allow_html=True) # HTML 렌더링을 위해 unsafe_allow_html 추가
def main():
    st.set_page_config(page_title="Oracle OCP AI 튜터", layout="wide", initial_sidebar_state="expanded")
    setup_database_tables()
    st.title("🚀 Oracle OCP AI 튜터")
    initialize_session_state()
    st.sidebar.title("메뉴")
    home_btn_type = "primary" if st.session_state.current_view in ['home', 'quiz', 'results'] else "secondary"
    notes_btn_type = "primary" if st.session_state.current_view == 'notes' else "secondary"
    analytics_btn_type = "primary" if st.session_state.current_view == 'analytics' else "secondary"
    manage_btn_type = "primary" if st.session_state.current_view == 'manage' else "secondary"
    if st.sidebar.button("📝 퀴즈 풀기", use_container_width=True, type=home_btn_type):
        st.session_state.current_view = 'home'
        st.session_state.questions_to_solve = []
        st.session_state.user_answers = {}
        st.session_state.current_question_index = 0
        st.rerun()
    if st.sidebar.button("📒 오답 노트", use_container_width=True, type=notes_btn_type):
        st.session_state.current_view = 'notes'
        st.rerun()
    if st.sidebar.button("📈 학습 통계", use_container_width=True, type=analytics_btn_type):
        st.session_state.current_view = 'analytics'
        st.rerun()
    if st.sidebar.button("⚙️ 설정 및 관리", use_container_width=True, type=manage_btn_type):
        st.session_state.current_view = 'manage'
        st.rerun()
    st.sidebar.write("---")
    st.sidebar.subheader("앱 관리")
    if st.sidebar.button("현재 학습 초기화", use_container_width=True):
        st.session_state.clear()
        st.toast("현재 학습 상태가 초기화되었습니다.")
        st.rerun()
    with st.sidebar.expander("⚠️ 전체 데이터 초기화 (주의)"):
        st.warning("모든 오답 기록과 AI 생성 문제를 영구적으로 삭제합니다.")
        if st.button("모든 학습 기록 삭제", type="primary", use_container_width=True):
            from db_utils import clear_all_modified_questions, get_db_connection
            conn = get_db_connection()
            conn.execute("DELETE FROM user_answers")
            conn.commit()
            conn.close()
            clear_all_modified_questions()
            st.toast("모든 학습 기록 및 AI 생성 문제가 영구적으로 삭제되었습니다.")
            st.session_state.clear()
            st.rerun()
    if st.session_state.current_view == 'home':
        render_home_page()
    elif st.session_state.current_view == 'quiz':
        render_quiz_page()
    elif st.session_state.current_view == 'results':
        render_results_page()
    elif st.session_state.current_view == 'notes':
        render_notes_page()
    elif st.session_state.current_view == 'manage':
        render_management_page()
    elif st.session_state.current_view == 'analytics':
        render_analytics_page()

if __name__ == "__main__":
    main()