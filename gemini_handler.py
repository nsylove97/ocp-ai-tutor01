# gemini_handler.py
"""
Google Gemini API와의 모든 상호작용을 담당하는 모듈.
문제 해설 생성, 문제 변형 등의 AI 기능을 수행합니다.
"""
import os
import json
import re
import google.generativeai as genai
from dotenv import load_dotenv
from google.api_core import exceptions

# --- Initialization ---
load_dotenv()

try:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY가 .env 파일에 설정되지 않았습니다.")
    genai.configure(api_key=api_key)
    
    # API 요청 시 안전 설정을 조정하여 콘텐츠 차단을 최소화
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
    model = genai.GenerativeModel('gemini-flash-lite-latest') 

except (ValueError, Exception) as e:
    model = None
    print(f"Gemini API 초기화 오류: {e}")

# --- Helper Functions ---
def _clean_and_parse_json(raw_text: str):
    """
    AI 응답 텍스트에서 JSON 객체만 안전하게 추출하고 파싱합니다.
    Markdown 코드 블록(```json ... ```)을 처리합니다.
    """
    if not isinstance(raw_text, str): return None
    
    match = re.search(r'```json\s*(\{.*\})\s*```', raw_text, re.DOTALL)
    json_text = match.group(1) if match else raw_text
    
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        # 중괄호로 시작하고 끝나는 부분만 다시 추출 시도
        start = json_text.find('{')
        end = json_text.rfind('}')
        if start != -1 and end != -1:
            try:
                return json.loads(json_text[start:end+1])
            except json.JSONDecodeError:
                return None
        return None

# --- Main API Functions ---
def generate_explanation(question_data: dict) -> dict:
    """Gemini를 사용하여 문제에 대한 상세한 해설을 생성합니다."""
    if not model: return {"error": "Gemini API가 설정되지 않았습니다."}

    try:
        question_text = question_data['question']
        options = json.loads(question_data['options'])
        answer = json.loads(question_data['answer'])
        options_str = "\n".join([f"{key}. {value}" for key, value in options.items()])
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return {"error": f"해설 생성을 위한 문제 데이터 파싱 오류: {e}"}

    prompt = f"""
    You are an instructor known for making students feel confident and smart. Your name is 'Gemini Tutor'.
    Explain the following Oracle OCP question for a beginner. The correct answer is {answer}.
    Do not use overly complex jargon without explaining it first.

    **Question:**
    {question_text}
    **Options:**
    {options_str}

    Please structure your explanation in three distinct parts as a JSON object, using Korean:
    1.  "analogy": A simple, easy-to-understand analogy.
    2.  "visualization": A text-based visualization.
    3.  "core_concepts": A clear summary of the key concepts, explaining why the correct answer is right and others are wrong.

    **Output Format (Strictly follow this JSON format):**
    {{
      "analogy": "...",
      "visualization": "...",
      "core_concepts": "..."
    }}
    """
    
    try:
        response = model.generate_content(prompt, safety_settings=safety_settings)
        parsed_json = _clean_and_parse_json(response.text)
        if parsed_json:
            return parsed_json
        return {"error": f"AI 응답에서 유효한 JSON을 파싱하지 못했습니다. 원본 응답:\n---\n{response.text}\n---"}

    except exceptions.InternalServerError as e:
        return {"error": f"AI 서버 내부 오류(500)가 발생했습니다. 잠시 후 다시 시도해주세요."}
    except exceptions.ResourceExhausted as e:
        return {"error": f"API 사용량 한도를 초과했습니다. Google Cloud 콘솔에서 확인해주세요."}
    except Exception as e:
        return {"error": f"해설 생성 중 예상치 못한 API 오류 발생: {e}"}


def generate_modified_question(original_question_data: dict) -> dict:
    """Gemini를 사용하여 기존 문제를 변형한 새로운 문제를 생성합니다."""
    if not model: return {"error": "Gemini API가 설정되지 않았습니다."}
    
    try:
        question_text = original_question_data['question']
        options = json.loads(original_question_data['options'])
        answer = json.loads(original_question_data['answer'])
        options_str = "\n".join([f"{key}. {value}" for key, value in options.items()])
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return {"error": f"문제 변형을 위한 원본 데이터 파싱 오류: {e}"}

    prompt = f"""
    You are an expert Oracle DBA exam question creator. Based on the provided question, create a new, similar one.
    
    **Instructions:**
    - Test the exact same core concept.
    - Change details like table/column names, and values.
    - The output MUST be a valid JSON object and nothing else.
    
    **One-shot Example:**
    **Input:**
    Question: Which query is valid for the EMPLOYEES table?
    Options: {{...}}
    Correct Answer: ["C"]
    
    **Expected Output (JSON only):**
    {{
      "question": "For the WORKERS table, which of the following SQL statements is correct?",
      "options": {{ "A": "...", "B": "...", "C": "...", "D": "...", "E": "..." }},
      "answer": ["B"]
    }}
    ---
    **Now, process the following real request:**
    **Input:**
    Question: {question_text}
    Options:
    {options_str}
    Correct Answer: {answer}

    **Expected Output (JSON only):**
    """
    
    try:
        response = model.generate_content(prompt, safety_settings=safety_settings)
        parsed_json = _clean_and_parse_json(response.text)
        
        if not parsed_json:
            return {"error": f"AI 응답에서 유효한 JSON을 파싱하지 못했습니다. 원본 응답:\n---\n{response.text}\n---"}

        if not all(k in parsed_json for k in ['question', 'options', 'answer']):
            return {"error": "AI가 생성한 데이터에 필수 필드('question', 'options', 'answer')가 누락되었습니다."}
        
        if not isinstance(parsed_json.get('answer'), list):
             parsed_json['answer'] = [str(parsed_json.get('answer'))]

        return parsed_json
 
    except exceptions.InternalServerError as e:
        return {"error": f"AI 서버 내부 오류(500)가 발생했습니다. 잠시 후 다시 시도해주세요."}
    except exceptions.ResourceExhausted as e:
        return {"error": f"API 사용량 한도를 초과했습니다. Google Cloud 콘솔에서 확인해주세요."}
    except Exception as e:
        return {"error": f"문제 변형 중 예상치 못한 API 오류 발생: {e}"}

def analyze_difficulty(question_text: str) -> str:
    """
    Gemini를 사용하여 문제 텍스트를 분석하고 난이도를 '쉬움', '보통', '어려움' 중 하나로 추정합니다.
    """
    if not model:
        print("Warning: Gemini API not configured. Defaulting difficulty to '보통'.")
        return '보통'

    prompt = f"""
    Analyze the difficulty of the following Oracle OCP exam question.
    Consider factors like complexity of the SQL query, subtlety of the concept, number of components involved, and depth of knowledge required.
    
    Based on your analysis, classify the difficulty into one of three levels: "쉬움", "보통", "어려움".
    Your answer must be ONLY ONE of these three words and nothing else.

    **Question to Analyze:**
    ---
    {question_text}
    ---

    **Difficulty (쉬움, 보통, or 어려움):**
    """
    
    try:
        response = model.generate_content(prompt, safety_settings=safety_settings)
        # 응답 텍스트에서 앞뒤 공백을 제거
        difficulty = response.text.strip()
        
        # 예상 답변 외의 값이 나오면 '보통'으로 강제
        if difficulty not in ['쉬움', '보통', '어려움']:
            return '보통'
        return difficulty
        
    except Exception as e:
        print(f"Difficulty analysis failed for a question: {e}")
        return '보통' # 오류 발생 시 기본값 반환

def get_chat_response(history: list, question: str) -> str:
    """
    대화 기록을 바탕으로 Gemini 채팅 모델의 응답을 생성합니다.
    """
    if not model:
        return "Gemini API가 설정되지 않았습니다."

    try:
        chat_model = genai.GenerativeModel('gemini-flash-lite-latest')
        chat = chat_model.start_chat(history=history)
        response = chat.send_message(question)
        return response.text
    except Exception as e:
        return f"AI 응답 생성 중 오류가 발생했습니다: {e}"