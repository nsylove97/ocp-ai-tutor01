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
# --- Minimal, safer CSS for iPhone Safari ---
try:
    st.markdown(
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
    <style>
    /* Safer, minimal CSS: avoid heavy fixed/inset rules that may break Safari */
    html, body, .main, .block-container {
        min-height: 100vh;
        -webkit-text-size-adjust: 100%;
    }
    /* 기본 버튼 스타일 최소화 (브라우저별 기본 동작을 많이 건드리지 않음) */
    div[data-testid="stButton"] > button {
        -webkit-tap-highlight-color: rgba(0,0,0,0);
        touch-action: manipulation;
    }
    /* 모달 안전 설정: position:fixed는 유지하되 inset/100vh 사용 최소화 */
    [data-modal-container], .stModal, .modal {
        position: fixed !important;
        left: 0; right: 0; top: 0; bottom: 0;
        display: flex !important;
        justify-content: center !important;
        align-items: center !important;
        background: rgba(0,0,0,0.45) !important;
        overflow: auto !important;
        -webkit-overflow-scrolling: touch !important;
        padding: env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left);
    }
    [data-modal-container] > div, .stModal > div {
        max-width: 900px;
        width: calc(100% - 2rem);
        max-height: calc(100% - 2rem);
        overflow: auto;
        background: #fff;
        padding: 1rem;
        border-radius: 8px;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )
except Exception as e:
    # CSS 주입 실패해도 앱 동작하도록 안전하게 무시하고 콘솔에 로깅
    print("UI CSS injection failed:", e)

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