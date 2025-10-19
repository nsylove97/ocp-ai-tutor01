# ui_components.py
"""
Streamlit UI 컴포넌트를 생성하는 함수들을 모아놓은 모듈.
문제 표시, 결과 표시 등 재사용 가능한 UI 로직을 담당합니다.
"""
import streamlit as st
import json
import os
from db_utils import get_question_by_id, save_user_answer

# --- CSS Injection ---
# 앱 전체에 적용될 커스텀 CSS 스타일을 한 번만 주입합니다.
# 이 코드는 파일이 임포트될 때 한 번만 실행됩니다.
st.markdown("""
<style>
/* Streamlit 버튼을 감싸는 div 컨테이너의 기본 여백을 줄여 흰 줄을 최소화 */
div[data-testid="stButton"] {
    margin-bottom: 10px;
}
/* 모든 버튼에 대한 기본 스타일 (카드 모양처럼) */
div[data-testid="stButton"] > button {
    width: 100%;
    text-align: left !important;
    padding: 1rem !important;
    border-radius: 0.5rem !important;
    margin-bottom: 0.5rem;
    color: #31333f !important;
    background-color: #ffffff !important;
    border: 1px solid #e6e6e6 !important;
    transition: all 0.2s ease-in-out;
    -webkit-transition: all 0.2s ease-in-out;
    touch-action: manipulation;
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
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    -webkit-box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}
/* 버튼 클릭 시 잠시 나타나는 포커스 테두리 */
div[data-testid="stButton"] > button:focus {
    outline: none !important;
    box-shadow: 0 0 0 2px rgba(28, 131, 225, 0.5) !important;
}

/* --- streamlit-modal 중앙 정렬 및 iOS 호환성 개선 CSS --- */
/* 1. 모달 배경을 화면 전체에 고정: inset 사용, overflow 및 터치 스크롤 허용 */
div[data-modal-container] {
    position: fixed; /* 화면 스크롤과 상관없이 위치 고정 */
    inset: 0; /* top:0; right:0; bottom:0; left:0; */
    /* 100vh/100vw 대신 inset/100% 조합을 사용하여 iOS 주소창 이슈 완화 */
    width: 100%;
    height: 100%;
    min-height: 100%;
    background-color: rgba(0, 0, 0, 0.5); /* 반투명 검은색 배경 */
    display: flex;
    justify-content: center; /* 수평 중앙 정렬 */
    align-items: center; /* 수직 중앙 정렬 */
    z-index: 9999; /* 다른 모든 요소들 위에 표시 */
    overflow: auto; /* 내부 컨텐츠가 클 때 스크롤 가능 */
    -webkit-overflow-scrolling: touch; /* iOS 부드러운 터치 스크롤 */
    padding: env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left);
}

/* 2. 실제 모달 팝업창 스타일 - 반응형 최대 너비/높이 및 내부 스크롤 허용 */
div[data-modal-container] > div[data-testid="stVerticalBlock"] {
    background-color: #ffffff;
    padding: 1.25rem;
    border-radius: 0.5rem;
    box-shadow: 0 8px 24px rgba(0,0,0,0.12);
    max-width: 900px;
    width: calc(100% - 2rem); /* 화면 여백 확보 */
    box-sizing: border-box;
    max-height: calc(100% - 2rem); /* 모바일에서 모달이 화면을 넘지 않도록 */
    overflow: auto;
    -webkit-overflow-scrolling: touch;
    margin: auto;
}

/* 작은 화면에서 여백을 더 확보 */
@media (max-width: 480px) {
    div[data-modal-container] > div[data-testid="stVerticalBlock"] {
        padding: 1rem;
        width: calc(100% - 1.5rem);
        border-radius: 0.5rem;
    }
}

/* 안전 영역 보정 (iPhone notch 등) */
body {
    padding-bottom: env(safe-area-inset-bottom, 0);
    padding-top: env(safe-area-inset-top, 0);
}
</style>
""", unsafe_allow_html=True)


# --- Helper Functions ---
def _handle_choice_selection(choice_key, answer_count):
    """선택지 클릭 시 호출되는 콜백. 사용자의 답변을 세션 상태에 업데이트합니다."""
    idx = st.session_state.current_question_index
    user_answers = st.session_state.user_answers.get(idx, [])

    if answer_count > 1: # 다중 선택
        if choice_key in user_answers: user_answers.remove(choice_key)
        else: user_answers.append(choice_key)
    else: # 단일 선택
        user_answers = [choice_key]
    
    st.session_state.user_answers[idx] = user_answers


# --- Main UI Functions ---
def display_question(question_data: dict, current_idx: int, total_questions: int):
    """
    클릭 가능한 '카드' 형태의 선택지를 포함한 퀴즈 문제를 표시합니다.
    """
    st.subheader(f"문제 {current_idx + 1}/{total_questions} (ID: {question_data['id']})")
    st.markdown(question_data['question'], unsafe_allow_html=True)
    
    media_url = question_data.get('media_url')
    if media_url and os.path.exists(media_url):
        media_type = question_data.get('media_type')
        if media_type == 'image': 
            st.image(media_url)
        elif media_type == 'video': 
            st.video(media_url)
    
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


def display_results(username: str, get_ai_explanation_func):
    """퀴즈 결과를 요약하고, 각 문제에 대한 상세 정보를 표시합니다."""
    
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