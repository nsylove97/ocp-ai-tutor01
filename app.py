#app.py
import streamlit as st
import random
import json
import pandas as pd
from gemini_handler import generate_explanation, generate_modified_question
from db_utils import get_all_question_ids, get_question_by_id, get_wrong_answers, save_modified_question
from ui_components import display_question, display_results
from db_utils import (
    get_all_question_ids, get_question_by_id, get_wrong_answers,
    save_modified_question, get_all_modified_questions,
    delete_wrong_answer, delete_modified_question, clear_all_modified_questions,
    get_stats, get_top_5_missed,
    setup_database_tables, load_original_questions_from_json,
    update_original_question, add_new_original_question
)

# --- AI 해설 함수에 캐싱 적용 ---
@st.cache_data
def get_ai_explanation(_q_id, _q_type):
    """캐시를 사용하여 AI 해설을 가져옵니다. DB 조회 실패 시 절대 None을 반환하지 않습니다."""
    question_data = get_question_by_id(_q_id, _q_type)
    
    # --- 여기가 핵심 수정 부분 ---
    if question_data:
        return generate_explanation(question_data)
    else:
        # DB에서 문제를 찾지 못하면, None 대신 명확한 에러 메시지가 담긴 딕셔너리를 반환
        return {"error": f"데이터베이스에서 해당 문제(ID: {_q_id}, Type: {_q_type})를 찾을 수 없어 해설을 생성할 수 없습니다."}

# --- 상태 관리 함수 ---
def initialize_session_state():
    """세션 상태를 초기화하는 함수"""
    if 'current_view' not in st.session_state:
        st.session_state.current_view = 'home' # home, quiz, results, notes
    if 'questions_to_solve' not in st.session_state:
        st.session_state.questions_to_solve = []
    if 'current_question_index' not in st.session_state:
        st.session_state.current_question_index = 0
    if 'user_answers' not in st.session_state:
        st.session_state.user_answers = {}

# --- 페이지 렌더링 함수 ---

def render_home_page():
    """초기 화면 (퀴즈 설정)을 렌더링"""
    st.header("📝 퀴즈 설정")
    
    # 퀴즈 모드 선택 (랜덤 vs. ID 지정)
    quiz_mode = st.radio("퀴즈 모드를 선택하세요:", ("랜덤 퀴즈", "ID로 문제 풀기"), key="quiz_mode_selector", horizontal=True)
    
    # 선택된 모드에 따라 다른 UI 표시
    if quiz_mode == "랜덤 퀴즈":
        num_questions = st.slider("풀고 싶은 문제 수를 선택하세요:", 1, 50, 10, key="num_questions_slider")
        quiz_type = st.radio("어떤 문제를 풀어볼까요?", ('기존 문제', '✨ AI 변형 문제'), key="quiz_type_selector")
    else: # "ID로 문제 풀기"
        question_id = st.number_input("풀고 싶은 원본 문제의 ID를 입력하세요:", min_value=1, step=1)

    if st.button("퀴즈 시작하기", type="primary"):
        # 퀴즈 시작 시 공통 상태 초기화
        st.session_state.questions_to_solve = []
        st.session_state.user_answers = {}
        st.session_state.current_question_index = 0
        
        should_rerun = False
        
        # 분기 처리
        if quiz_mode == "랜덤 퀴즈":
            if quiz_type == '기존 문제':
                # ... (기존 랜덤 퀴즈 - 기존 문제 로직과 동일)
                all_ids = get_all_question_ids('original')
                if not all_ids:
                    st.error("데이터베이스에 원본 문제가 없습니다. 먼저 `db_setup.py`를 실행해주세요.")
                    return
                selected_ids = random.sample(all_ids, min(num_questions, len(all_ids)))
                st.session_state.questions_to_solve = [{'id': q_id, 'type': 'original'} for q_id in selected_ids]
                st.session_state.current_view = 'quiz'
                should_rerun = True
            
            elif quiz_type == '✨ AI 변형 문제':
                # ... (기존 랜덤 퀴즈 - AI 변형 문제 로직과 동일)
                with st.spinner(f"{num_questions}개의 새로운 변형 문제를 AI가 생성 중입니다..."):
                    # ... (생략된 코드는 이전 버전과 동일)
                    pass # 이 부분은 이전 코드 그대로 두시면 됩니다.

        else: # "ID로 문제 풀기"
            # 입력된 ID의 문제가 DB에 실제로 존재하는지 확인
            target_question = get_question_by_id(question_id, 'original')
            if target_question:
                st.session_state.questions_to_solve = [{'id': question_id, 'type': 'original'}]
                st.session_state.current_view = 'quiz'
                should_rerun = True
            else:
                st.error(f"ID {question_id}에 해당하는 원본 문제를 찾을 수 없습니다. ID를 다시 확인해주세요.")

        if should_rerun:
            st.rerun()

def render_quiz_page():
    idx = st.session_state.current_question_index
    total_questions = len(st.session_state.questions_to_solve)

    # 진행률 바 추가
    progress_percent = (idx + 1) / total_questions
    st.progress(progress_percent, text=f"{idx + 1}/{total_questions} 문제 진행 중...")
    """퀴즈 진행 화면을 렌더링"""
    if not st.session_state.questions_to_solve:
        st.warning("풀 문제가 없습니다. 홈 화면으로 돌아가 퀴즈를 다시 시작해주세요.")
        if st.button("홈으로 돌아가기"):
            st.session_state.current_view = 'home'
            st.rerun()
        return

    idx = st.session_state.current_question_index
    total_questions = len(st.session_state.questions_to_solve)
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
    """오답 노트 화면을 렌더링"""
    st.header("📒 오답 노트")
    wrong_answers = get_wrong_answers()

    if not wrong_answers:
        st.toast("🎉 축하합니다! 틀린 문제가 없습니다.")
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
                    st.markdown(question['question'])
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
    """결과 페이지를 렌더링"""
    display_results(get_ai_explanation)
    if st.button("새 퀴즈 시작하기"):
        st.session_state.current_view = 'home'
        st.rerun()

# app.py

# ... (파일 상단 import문 및 다른 함수 정의)

def render_management_page():
    """오답 노트 및 AI 생성 문제를 관리하는 페이지"""
    st.header("⚙️ 설정 및 관리")

    # 탭 순서를 변경하여 원본 문제 관리를 가장 앞에 배치
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["원본 문제 데이터", "문제 추가 (원본)", "문제 편집 (원본)", "오답 노트 관리", "AI 변형 문제 관리"])

    # --- 탭 1: 원본 문제 데이터 관리 ---
    with tab1:
        st.subheader("📚 원본 문제 데이터 관리")
        st.info("배포된 환경에서 처음 앱을 사용하거나 원본 문제를 초기화하고 싶을 때 사용하세요. 기존 문제는 모두 삭제되고 새로 로드됩니다.")
        
        # 현재 DB에 있는 원본 문제 수 확인
        num_original_questions = len(get_all_question_ids('original'))
        st.metric("현재 저장된 원본 문제 수", f"{num_original_questions} 개")

        if st.button("JSON 파일에서 원본 문제 불러오기", type="primary"):
            with st.spinner("`questions_final.json` 파일을 읽어 데이터베이스를 설정하는 중입니다..."):
                # 1. 테이블이 없을 수도 있으니 먼저 테이블 구조부터 확인/생성
                setup_database_tables()
                # 2. JSON 파일에서 데이터 로드
                count, error = load_original_questions_from_json()

                if error:
                    st.error(f"문제 로딩 실패: {error}")
                else:
                    st.toast(f"성공적으로 {count}개의 원본 문제를 데이터베이스에 불러왔습니다!")
                    # 상태를 갱신하기 위해 새로고침
                    st.rerun()

    # --- 탭 2: 문제 추가 (원본) ---
    with tab2:
        st.subheader("➕ 새로운 원본 문제 추가")
        st.info("새로운 OCP 문제를 직접 추가하여 나만의 문제 은행을 만드세요.")

        with st.form(key="add_form"):
            # 문제 내용 입력
            new_question_text = st.text_area("질문 내용:", height=150, placeholder="예: Which three statements are true...?")
            
            # 선택지 입력 (기본으로 5개 제공)
            new_options = {}
            option_letters = ["A", "B", "C", "D", "E"]
            for letter in option_letters:
                new_options[letter] = st.text_input(f"선택지 {letter}:", key=f"new_option_{letter}")
            
            # 정답 선택
            # 비어있는 선택지는 multiselect 옵션에서 제외
            valid_options = [letter for letter, text in new_options.items() if text.strip()]
            new_answer = st.multiselect("정답 선택:", options=valid_options)
            
            submitted = st.form_submit_button("새 문제 추가하기")

            if submitted:
                # 유효성 검사
                if not new_question_text.strip():
                    st.error("질문 내용을 입력해야 합니다.")
                elif not all(text.strip() for text in new_options.values() if text):
                    st.error("선택지 내용을 모두 입력해야 합니다. (최소 1개 이상)")
                elif not new_answer:
                    st.error("정답을 하나 이상 선택해야 합니다.")
                else:
                    # DB에 새 문제 추가
                    new_id = add_new_original_question(new_question_text, new_options, new_answer)
                    st.toast(f"성공적으로 새로운 문제(ID: {new_id})를 추가했습니다!")
                    st.balloons() # 축하!

    # --- 탭 3: 문제 편집 ---
    with tab3:
        st.subheader("✏️ 원본 문제 편집")
        
        # 편집할 문제 ID 입력받기
        edit_id = st.number_input("편집할 원본 문제의 ID를 입력하세요:", min_value=1, step=1, key="edit_question_id")
        
        if edit_id:
            # DB에서 해당 문제 데이터 가져오기
            question_to_edit = get_question_by_id(edit_id, 'original')

            if not question_to_edit:
                st.warning("해당 ID의 문제를 찾을 수 없습니다.")
            else:
                st.write("---")
                st.write(f"**ID {edit_id} 문제 수정:**")

                # form을 사용하여 여러 입력 필드를 그룹화하고 한 번에 제출
                with st.form(key="edit_form"):
                    # 현재 데이터를 기본값으로 설정하여 UI에 표시
                    current_options = json.loads(question_to_edit['options'])
                    current_answer = json.loads(question_to_edit['answer'])

                    # 편집 가능한 입력 필드들
                    edited_question_text = st.text_area("질문 내용:", value=question_to_edit['question'], height=150)
                    
                    edited_options = {}
                    for key, value in current_options.items():
                        edited_options[key] = st.text_input(f"선택지 {key}:", value=value, key=f"option_{key}")
                    
                    edited_answer = st.multiselect("정답 선택:", options=list(edited_options.keys()), default=current_answer)
                    
                    # '변경사항 저장' 버튼
                    submitted = st.form_submit_button("변경사항 저장")

                    if submitted:
                        # 버튼이 클릭되면, 입력된 값으로 DB 업데이트
                        update_original_question(edit_id, edited_question_text, edited_options, edited_answer)
                        st.toast(f"ID {edit_id} 문제가 성공적으로 업데이트되었습니다!")
                        # 캐시된 데이터를 초기화하여 변경사항이 즉시 반영되도록 함
                        st.cache_data.clear()
 
    # --- 탭 4: 오답 노트 관리 ---
    with tab4:
        st.subheader("📒 오답 노트 관리")
        wrong_answers = get_wrong_answers()
        
        if not wrong_answers:
            st.info("관리할 오답 노트가 없습니다.")
        else:
            st.warning(f"총 {len(wrong_answers)}개의 오답 기록이 있습니다. 이제 완전히 이해한 문제는 목록에서 삭제할 수 있습니다.")
            st.write("---")
            
            # 각 오답 기록을 순회하며 표시
            for q_info in wrong_answers:
                # 오답 문제의 상세 정보 가져오기
                question = get_question_by_id(q_info['question_id'], q_info['question_type'])
                
                # DB에서 문제가 삭제되었을 경우를 대비한 방어 코드
                if question:
                    # 컬럼을 사용하여 레이아웃 정리
                    col1, col2 = st.columns([4, 1])
                    
                    with col1:
                        # 문제 내용을 간략하게 표시
                        question_preview = question['question'].replace('\n', ' ').strip()
                        st.text(f"ID {question['id']} ({q_info['question_type']}): {question_preview[:70]}...")
                    
                    with col2:
                        # 고유한 key를 생성하여 각 버튼이 독립적으로 작동하도록 함
                        button_key = f"del_wrong_{q_info['question_id']}_{q_info['question_type']}"
                        
                        if st.button("삭제", key=button_key, type="secondary"):
                            # '삭제' 버튼 클릭 시 해당 오답 기록 삭제 함수 호출
                            delete_wrong_answer(q_info['question_id'], q_info['question_type'])
                            st.toast(f"ID {question['id']} 오답 기록이 삭제되었습니다.")
                            
                            # 목록을 즉시 갱신하기 위해 새로고침
                            st.rerun()

    # --- 탭 5: AI 변형 문제 관리 ---
    with tab5:
        st.subheader("✨ AI 변형 문제 관리")
        modified_questions = get_all_modified_questions()
        
        if not modified_questions:
            st.info("관리할 AI 변형 문제가 없습니다.")
        else:
            st.warning("여기서 삭제된 AI 변형 문제는 복구할 수 없습니다.")
            
            # 모든 변형 문제를 한 번에 삭제하는 버튼
            if st.button("모든 변형 문제 삭제", type="primary"):
                clear_all_modified_questions()
                st.toast("모든 AI 변형 문제가 삭제되었습니다.")
                st.rerun()
            
            st.write("---")

            # 각 변형 문제를 순회하며 표시
            for mq in modified_questions:
                col1, col2 = st.columns([4, 1])
                
                with col1:
                    # 문제 내용을 간략하게 표시
                    question_preview = mq['question'].replace('\n', ' ').strip()
                    st.text(f"ID {mq['id']}: {question_preview[:70]}...")
                
                with col2:
                    # 고유한 key를 생성
                    button_key = f"del_mod_{mq['id']}"
                    
                    if st.button("삭제", key=button_key, type="secondary"):
                        # '삭제' 버튼 클릭 시 해당 변형 문제 삭제 함수 호출
                        delete_modified_question(mq['id'])
                        st.toast(f"ID {mq['id']} 변형 문제가 삭제되었습니다.")
                        
                        # 목록을 즉시 갱신하기 위해 새로고침
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
                st.markdown(row['question'])

# --- 메인 애플리케이션 로직 ---
def main():
    """메인 실행 함수"""
    st.set_page_config(page_title="Oracle OCP AI 튜터", layout="wide", initial_sidebar_state="expanded")
    
    setup_database_tables()

    st.title("🚀 Oracle OCP AI 튜터")
    
    initialize_session_state()

    st.sidebar.title("메뉴")
    
    # 현재 뷰 상태에 따라 버튼 타입을 다르게 설정하여 시각적 피드백 제공
    home_btn_type = "primary" if st.session_state.current_view in ['home', 'quiz', 'results'] else "secondary"
    notes_btn_type = "primary" if st.session_state.current_view == 'notes' else "secondary"
    analytics_btn_type = "primary" if st.session_state.current_view == 'analytics' else "secondary"
    manage_btn_type = "primary" if st.session_state.current_view == 'manage' else "secondary"

        # 퀴즈 풀기
    if st.sidebar.button("📝 퀴즈 풀기", use_container_width=True, type=home_btn_type):
        st.session_state.current_view = 'home'
        st.session_state.questions_to_solve = []
        st.session_state.user_answers = {}
        st.session_state.current_question_index = 0
        st.rerun()

        # 오답 노트  
    if st.sidebar.button("📒 오답 노트", use_container_width=True, type=notes_btn_type):
        st.session_state.current_view = 'notes'
        st.rerun()
        
        # 학습 통계
    if st.sidebar.button("📈 학습 통계", use_container_width=True, type=analytics_btn_type):
        st.session_state.current_view = 'analytics'
        st.rerun()

        # "설정 및 관리" 메뉴 추가
    if st.sidebar.button("⚙️ 설정 및 관리", use_container_width=True, type=manage_btn_type):
        st.session_state.current_view = 'manage'
        st.rerun()



    # --- 사이드바 하단에 초기화/종료 버튼 추가 ---
    st.sidebar.write("---")
    st.sidebar.subheader("앱 관리")

    # 현재 세션(화면 상태)만 초기화
    if st.sidebar.button("현재 학습 초기화", use_container_width=True):
        st.session_state.clear() # 모든 세션 상태를 비움
        st.toast("현재 학습 상태가 초기화되었습니다.")
        st.rerun()

    # 데이터베이스까지 초기화 (주의 필요)
    with st.sidebar.expander("⚠️ 전체 데이터 초기화 (주의)"):
        st.warning("이 버튼은 모든 오답 기록과 AI 생성 문제를 영구적으로 삭제합니다. 신중하게 사용하세요.")
        if st.button("모든 학습 기록 삭제", type="primary", use_container_width=True):
            # db_utils.py에 이 기능을 수행할 함수를 만들어야 합니다.
            # 우선은 clear_all_modified_questions를 재활용합니다.
            from db_utils import clear_all_modified_questions, get_db_connection
            
            # 오답 기록 전체 삭제
            conn = get_db_connection()
            conn.execute("DELETE FROM user_answers")
            conn.commit()
            conn.close()
            
            # 변형 문제 전체 삭제
            clear_all_modified_questions()
            
            st.toast("모든 학습 기록 및 AI 생성 문제가 영구적으로 삭제되었습니다.")
            st.session_state.clear()
            st.rerun()


    # 현재 뷰에 따라 적절한 페이지 렌더링
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