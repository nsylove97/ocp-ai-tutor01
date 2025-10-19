# ui_components.py
import streamlit as st
import json
import streamlit_shadcn_ui as ui

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
        
        # shadcn.card 컴포넌트를 사용하여 선택지를 감쌉니다.
        # variant 속성을 이용해 선택 상태에 따라 다른 스타일을 적용합니다.
        # 'default'는 일반 상태, 'secondary'는 선택된 상태로 활용.
        with ui.card(
            key=f"card_{key}_{current_idx}",
            variant="secondary" if is_selected else "default",
            # on_click 콜백을 사용하여 클릭 이벤트를 처리합니다.
            # args를 통해 클릭된 선택지의 key와 문제의 answer_count를 전달합니다.
            on_click=handle_choice_selection,
            args=(key, answer_count)
        ):
            # 카드 안에 선택지 내용을 표시합니다.
            st.markdown(f"**{key}.** {value}")

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