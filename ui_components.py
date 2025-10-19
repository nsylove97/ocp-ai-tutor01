# ui_components.py
import streamlit as st
import json

# --- CSS 스타일 정의 ---
# 선택된 항목에 적용할 스타일과 컨테이너의 기본 스타일을 정의합니다.
SELECTED_CHOICE_STYLE = """
    border: 2px solid #1c83e1;
    background-color: #e5f1fc;
    border-radius: 10px;
    padding: 15px;
    margin-bottom: 10px;
"""

DEFAULT_CHOICE_STYLE = """
    border: 1px solid #e6e6e6;
    background-color: #fafafa;
    border-radius: 10px;
    padding: 15px;
    margin-bottom: 10px;
"""

def handle_choice_selection(choice_key, answer_count):
    """선택지 클릭을 처리하는 콜백 함수"""
    # 현재 문제의 인덱스와 사용자 답변 상태를 가져옴
    idx = st.session_state.current_question_index
    user_answers_for_current_q = st.session_state.user_answers.get(idx, [])

    if answer_count > 1: # 다중 선택 모드
        # 이미 선택된 것이면 제거(토글), 아니면 추가
        if choice_key in user_answers_for_current_q:
            user_answers_for_current_q.remove(choice_key)
        else:
            user_answers_for_current_q.append(choice_key)
    else: # 단일 선택 모드
        # 항상 새로운 선택으로 덮어씀
        user_answers_for_current_q = [choice_key]
    
    # 변경된 답변을 세션 상태에 다시 저장
    st.session_state.user_answers[idx] = user_answers_for_current_q

def display_question(question_data, current_idx, total_questions):
    """
    클릭 가능한 선택지를 포함한 퀴즈 문제 하나를 화면에 표시합니다.
    (기존 Radio/Multiselect 로직을 완전히 대체)
    """
    # ... (상단부는 이전과 동일: ID 표시, 질문/미디어 렌더링)
    question_id_text = f" (문제 ID: {question_data['id']})"
    st.subheader(f"문제 {current_idx + 1}/{total_questions}{question_id_text}")
    st.markdown(question_data['question'], unsafe_allow_html=True)
    if question_data.get('media_url'):
        # ... (미디어 표시 로직)
    st.write("---")

    # --- 여기가 핵심 변경 부분 ---
    options = json.loads(question_data['options'])
    try:
        answer_count = len(json.loads(question_data['answer']))
        if answer_count == 0: answer_count = 1
    except (json.JSONDecodeError, TypeError):
        answer_count = 1

    if answer_count > 1:
        st.info(f"**정답 {answer_count}개를 고르세요.** (선택지를 다시 클릭하면 해제됩니다)")
    else:
        st.info("**정답 1개를 고르세요.**")
    
    # 현재 문제에 대한 사용자의 선택을 가져옴
    user_selection = st.session_state.user_answers.get(current_idx, [])

    # 각 선택지를 순회하며 클릭 가능한 컨테이너 생성
    for key, value in options.items():
        # 현재 선택지가 사용자에 의해 선택되었는지 확인
        is_selected = key in user_selection
        
        # 선택 상태에 따라 다른 스타일 적용
        style = SELECTED_CHOICE_STYLE if is_selected else DEFAULT_CHOICE_STYLE
        
        # 각 선택지를 고유한 컨테이너에 담음
        with st.container():
            # st.markdown을 사용하여 컨테이너에 직접 스타일 적용 (약간의 해킹)
            st.markdown(f'<div style="{style}">', unsafe_allow_html=True)
            
            # 버튼을 만들어 클릭 이벤트를 감지
            if st.button(f"{key}. {value}", key=f"choice_{key}_{current_idx}", use_container_width=True):
                # 버튼이 클릭되면 콜백 함수를 직접 호출하여 상태 변경
                # (on_click은 rerun을 유발하므로, 여기서는 직접 호출)
                handle_choice_selection(key, answer_count)
                st.rerun() # 선택 상태를 즉시 UI에 반영하기 위해 rerun

            st.markdown('</div>', unsafe_allow_html=True)

def display_results(get_ai_explanation_func):
    """퀴즈 결과를 화면에 표시합니다."""
    st.header("📊 퀴즈 결과")
    correct_count = 0
    
    for i, q_info in enumerate(st.session_state.questions_to_solve):
        from db_utils import get_question_by_id, save_user_answer # 순환 참조 방지를 위해 함수 내에서 임포트
        
        question = get_question_by_id(q_info['id'], q_info['type'])
        options = json.loads(question['options'])
        
        try:
            correct_answer = sorted(json.loads(question['answer']))
        except (json.JSONDecodeError, TypeError):
            correct_answer = [] # 정답 정보가 잘못된 경우
        
        user_answer = sorted(st.session_state.user_answers.get(i, []))
        is_correct = (user_answer == correct_answer and correct_answer != [])

        with st.expander(f"문제 {i+1}: {'✅ 정답' if is_correct else '❌ 오답'}", expanded=not is_correct):
            st.markdown(question['question'])
            st.write("**정답:**", ", ".join(correct_answer))
            st.write("**나의 답:**", ", ".join(user_answer) if user_answer else "선택 안 함")
            
            if st.button("🤖 AI 해설 보기", key=f"exp_{q_info['id']}_{i}"):
                with st.spinner("AI가 열심히 해설을 만들고 있어요..."):
                    explanation = get_ai_explanation_func(q_info['id'], q_info['type'])
                    
                    # ui_components.py의 display_results 함수 내 AI 해설 보기 버튼 부분
                    explanation = get_ai_explanation_func(q_info['id'], q_info['type'])
                    error_message = explanation.get('error') if explanation else "해설 정보를 가져오지 못했습니다."

                    if error_message:
                        st.error(error_message)
                    else:
                        st.info(f"**💡 쉬운 비유**\n\n{explanation.get('analogy', '내용 없음')}")
                        st.info(f"**🖼️ 텍스트 시각화**\n\n```\n{explanation.get('visualization', '내용 없음')}\n```")
                        st.info(f"**🔑 핵심 개념 정리**\n\n{explanation.get('core_concepts', '내용 없음')}")

                        
        if is_correct:
            correct_count += 1
        else:
            save_user_answer(q_info['id'], q_info['type'], user_answer, is_correct=False)
    
    total_questions = len(st.session_state.questions_to_solve)
    if total_questions > 0:
        score = (correct_count / total_questions) * 100
        st.title(f"총점: {score:.2f}점 ({correct_count}/{total_questions}개 정답)")
        if is_correct:
            correct_count += 1
        else:
            save_user_answer(q_info['id'], q_info['type'], user_answer, is_correct=False)
    
    total_questions = len(st.session_state.questions_to_solve)
    if total_questions > 0:
        score = (correct_count / total_questions) * 100
        st.title(f"총점: {score:.2f}점 ({correct_count}/{total_questions}개 정답)")