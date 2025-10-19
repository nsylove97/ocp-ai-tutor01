# ui_components.py
import streamlit as st
import json

# --- CSS 스타일 정의 ---
st.markdown("""
<style>
/* Streamlit 버튼을 감싸는 div 컨테이너의 기본 여백을 줄여 흰 줄을 최소화 */
div.stButton {
    margin-bottom: 10px;
}

/* 모든 버튼에 대한 기본 스타일 (카드 모양처럼) */
.stButton > button {
    width: 100%;
    text-align: left !important; /* 텍스트 왼쪽 정렬 */
    padding: 15px !important;
    border-radius: 10px !important;
    border: 1px solid #e6e6e6 !important;
    background-color: #fafafa !important;
    color: #31333f !important; /* 기본 글자색 */
    transition: all 0.2s ease-in-out; /* 부드러운 전환 효과 */
}
/* 버튼 위에 마우스를 올렸을 때 */
.stButton > button:hover {
    border-color: #1c83e1 !important;
    background-color: #f0f2f6 !important;
}

/* --- 핵심: 선택된 상태의 버튼 스타일 --- */
/* type="primary"로 지정된 버튼에만 이 스타일을 적용합니다. */
.stButton > button[kind="primary"] {
    border: 2px solid #1c83e1 !important;
    background-color: #e5f1fc !important;
}

/* 버튼이 비활성화되었을 때 (현재는 사용 안함) */
.stButton > button:disabled {
    background-color: #f0f2f6 !important;
    color: #a3a3a3 !important;
    border-color: #e6e6e6 !important;
}
</style>
""", unsafe_allow_html=True)

def handle_choice_selection(choice_key, answer_count):
    """선택지 클릭을 처리하는 콜백 함수 (이전과 동일)"""
    idx = st.session_state.current_question_index
    user_answers_for_current_q = st.session_state.user_answers.get(idx, [])

    if answer_count > 1:
        if choice_key in user_answers_for_current_q:
            user_answers_for_current_q.remove(choice_key)
        else:
            user_answers_for_current_q.append(choice_key)
    else:
        user_answers_for_current_q = [choice_key]
    
    st.session_state.user_answers[idx] = user_answers_for_current_q

def display_question(question_data, current_idx, total_questions):
    """
    클릭 가능한 선택지를 포함한 퀴즈 문제 하나를 화면에 표시합니다.
    """
    question_id_text = f" (문제 ID: {question_data['id']})"
    st.subheader(f"문제 {current_idx + 1}/{total_questions}{question_id_text}")
    st.markdown(question_data['question'], unsafe_allow_html=True)
    
    # if 문 다음에 실행될 코드 블록을 올바르게 들여쓰기 합니다.
    if question_data.get('media_url'):
        media_type = question_data.get('media_type')
        media_url = question_data.get('media_url')
        if media_type == 'image':
            # st.image가 존재하지 않는 파일을 열려고 시도할 때 발생하는 오류 방지
            try:
                st.image(media_url)
            except Exception as e:
                st.warning(f"이미지 파일을 불러오는 데 실패했습니다: {media_url} ({e})")
        elif media_type == 'video':
            try:
                st.video(media_url)
            except Exception as e:
                st.warning(f"비디오 파일을 불러오는 데 실패했습니다: {media_url} ({e})")
    # --- 여기까지 ---

    st.write("---")
   
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
    
    user_selection = st.session_state.user_answers.get(current_idx, [])
    
    # 각 선택지를 순회하며 클릭 가능한 '카드' 생성
    for key, value in options.items():
        is_selected = key in user_selection
        
        # 선택 상태에 따라 버튼의 type을 동적으로 결정
        # 선택됨 -> 'primary', 선택 안됨 -> 'secondary'
        button_type = "primary" if is_selected else "secondary"
        
        # st.button을 생성하고, 클릭 시 콜백 함수를 실행
        if st.button(
            label=f"{key}. {value}", 
            key=f"choice_{key}_{current_idx}", 
            use_container_width=True,
            type=button_type, # <--- 여기가 핵심!
            on_click=handle_choice_selection,
            args=(key, answer_count)
        ):
            # on_click 콜백이 실행된 후 Streamlit은 자동으로 rerun을 수행하므로
            # 이 블록 안에 별도의 코드를 넣을 필요가 없습니다.
            pass


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