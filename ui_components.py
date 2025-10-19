# ui_components.py 
import streamlit as st
import json
import os

# --- CSS Injection ---
# ui_components.py
import streamlit as st
import json
import os

# --- CSS Injection (Cross-browser compatible version) ---
st.markdown("""
<style>
/* 
  div[data-testid="stButton"]는 Streamlit이 버튼을 감싸는 div에 부여하는
  고유한 속성으로, 더 안정적인 선택자(selector)입니다. 
*/
div[data-testid="stButton"] > button {
    /* 기본 레이아웃 및 디자인 */
    width: 100%;
    text-align: left !important;
    padding: 1rem !important; /* rem 단위가 모바일에서 더 일관적입니다. */
    border-radius: 0.5rem !important;
    margin-bottom: 0.5rem; /* 버튼 사이의 간격 */
    
    /* 색상 및 테두리 */
    color: #31333f !important;
    background-color: #ffffff !important; /* 기본 배경을 흰색으로 변경 */
    border: 1px solid #e6e6e6 !important;
    
    /* 애니메이션 */
    transition: all 0.2s ease-in-out;
    -webkit-transition: all 0.2s ease-in-out; /* Safari 호환성을 위한 접두사 */
}

/* 마우스 호버 시 효과 */
div[data-testid="stButton"] > button:hover {
    border-color: #1c83e1 !important;
    background-color: #f0f2f6 !important;
}

/* '선택됨' 상태 (type="primary") */
div[data-testid="stButton"] > button[kind="primary"] {
    border: 2px solid #1c83e1 !important;
    background-color: #e5f1fc !important;
    /* 선택 시 그림자 효과를 주어 입체감 부여 */
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    -webkit-box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); /* Safari 호환성 */
}

/* 버튼 클릭 시 잠시 나타나는 포커스 테두리 제거 (선택 사항) */
div[data-testid="stButton"] > button:focus {
    outline: none !important;
    box-shadow: 0 0 0 2px rgba(28, 131, 225, 0.5) !important;
}
</style>
""", unsafe_allow_html=True)


def _handle_choice_selection(choice_key, answer_count):
    """선택지 클릭 시 호출되는 콜백. 사용자의 답변을 세션 상태에 업데이트합니다."""
    idx = st.session_state.current_question_index
    user_answers = st.session_state.user_answers.get(idx, [])

    if answer_count > 1:
        if choice_key in user_answers: user_answers.remove(choice_key)
        else: user_answers.append(choice_key)
    else:
        user_answers = [choice_key]
    
    st.session_state.user_answers[idx] = user_answers


def display_question(question_data: dict, current_idx: int, total_questions: int):
    """클릭 가능한 '카드' 형태의 선택지를 포함한 퀴즈 문제를 표시합니다."""
    st.subheader(f"문제 {current_idx + 1}/{total_questions} (ID: {question_data['id']})")
    st.markdown(question_data['question'], unsafe_allow_html=True)
    
    media_url = question_data.get('media_url')
    if media_url and os.path.exists(media_url):
        media_type = question_data.get('media_type')
        if media_type == 'image': st.image(media_url)
        elif media_type == 'video': st.video(media_url)
    
    st.write("---")
   
    try:
        options = json.loads(question_data['options'])
        answer_count = len(json.loads(question_data['answer'])) or 1
    except (json.JSONDecodeError, TypeError):
        options, answer_count = {}, 1

    st.info(f"**정답 {answer_count}개를 고르세요.**" + (" (다시 클릭하면 해제)" if answer_count > 1 else ""))
    
    user_selection = st.session_state.user_answers.get(current_idx, [])
    
    for key, value in options.items():
        is_selected = key in user_selection
        st.button(
            label=f"{key}. {value}", 
            key=f"choice_{key}_{current_idx}", 
            use_container_width=True,
            type="primary" if is_selected else "secondary",
            on_click=_handle_choice_selection,
            args=(key, answer_count)
        )


def display_results(username, get_ai_explanation_func):
    """퀴즈 결과를 요약하고, 각 문제에 대한 상세 정보를 표시합니다."""
    
    # 순환 참조를 피하기 위해, 함수가 실제로 필요할 때 함수 내부에서 임포트합니다.
    from db_utils import get_question_by_id, save_user_answer
    # --- 여기까지 ---
    
    st.header("📊 퀴즈 결과")
    correct_count = 0
    
    for i, q_info in enumerate(st.session_state.questions_to_solve):
        question = get_question_by_id(q_info['id'], q_info['type'])
        if not question:
            st.warning(f"결과 표시 중 문제(ID: {q_info['id']})를 찾을 수 없습니다.")
            continue

        try:
            options = json.loads(question['options'])
            correct_answer = sorted(json.loads(question['answer']))
        except (json.JSONDecodeError, TypeError):
            options, correct_answer = {}, []

        user_answer = sorted(st.session_state.user_answers.get(i, []))
        is_correct = (user_answer == correct_answer and correct_answer != [])

        with st.expander(f"문제 {i+1} (ID: {question['id']}): {'✅ 정답' if is_correct else '❌ 오답'}", expanded=not is_correct):
            st.markdown(question['question'], unsafe_allow_html=True)
            st.write("**정답:**", ", ".join(correct_answer))
            st.write("**나의 답:**", ", ".join(user_answer) if user_answer else "선택 안 함")
            
            if st.button("🤖 AI 해설 보기", key=f"exp_{q_info['id']}_{i}"):
                with st.spinner("AI 튜터가 해설을 만들고 있어요..."):
                    explanation = get_ai_explanation_func(q_info['id'], q_info['type'])
                    error_msg = explanation.get('error') if explanation else "해설을 가져오지 못했습니다."
                    if error_msg:
                        st.error(error_msg)
                    else:
                        st.info(f"**💡 쉬운 비유:**\n\n{explanation.get('analogy', 'N/A')}")
                        st.info(f"**🖼️ 텍스트 시각화:**\n\n```\n{explanation.get('visualization', 'N/A')}\n```")
                        st.info(f"**🔑 핵심 개념:**\n\n{explanation.get('core_concepts', 'N/A')}")
                        
        if is_correct:
            correct_count += 1
        else:
            save_user_answer(username, q_info['id'], q_info['type'], user_answer, is_correct=False)
    
    total_questions = len(st.session_state.questions_to_solve)
    if total_questions > 0:
        score = (correct_count / total_questions) * 100
        st.title(f"총점: {score:.2f}점 ({correct_count}/{total_questions}개 정답)")