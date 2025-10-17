# ui_components.py
import streamlit as st
import json

def display_question(question_data, current_idx, total_questions):
    """퀴즈 문제 하나를 화면에 표시하고 사용자의 선택을 반환합니다."""
    q_info = st.session_state.questions_to_solve[current_idx]  
    options = json.loads(question_data['options'])
    # 정답이 비어있거나 유효하지 않은 JSON일 경우 기본값 1로 처리
    try:
        answer_count = len(json.loads(question_data['answer']))
        if answer_count == 0: answer_count = 1
    except (json.JSONDecodeError, TypeError):
        answer_count = 1
    # 문제 번호(ID)와 진행 상황을 함께 보여줍니다.
    question_id_text = f" (문제 ID: {question_data['id']})"
    st.subheader(f"문제 {current_idx + 1}/{total_questions}{question_id_text}")
    st.markdown(question_data['question'])
    st.write("---")

    user_choice = []
    default_choice = st.session_state.user_answers.get(current_idx, [])
    
    # 안정성 강화: default_choice가 options의 key 중에 있는지 확인
    valid_default = [opt for opt in default_choice if opt in options]

    if answer_count > 1:
        st.write(f"**정답 {answer_count}개를 고르세요.**")
        user_choice = st.multiselect("답:", options.keys(), default=valid_default, format_func=lambda x: f"{x}. {options[x]}")
    else:
        # 안정성 강화: 라디오 버튼의 기본 인덱스가 유효한지 확인
        current_selection = valid_default[0] if valid_default and valid_default[0] in options else None
        index = list(options.keys()).index(current_selection) if current_selection else 0
        
        radio_key = f"radio_{q_info['id']}_{current_idx}"
        user_choice_single = st.radio("답:", options.keys(), index=index, key=radio_key, format_func=lambda x: f"{x}. {options[x]}")
        if user_choice_single:
            user_choice = [user_choice_single]
    
    st.session_state.user_answers[current_idx] = user_choice

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