# gemini_handler.py 
import os
import json
import re
import google.generativeai as genai
from dotenv import load_dotenv
from google.api_core import exceptions

load_dotenv()

try:
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
    model = genai.GenerativeModel('gemini-flash-lite-latest')
except Exception as e:
    model = None

def clean_and_parse_json(raw_text: str):
    if not isinstance(raw_text, str):
        return None
    match = re.search(r'```json\s*(\{.*\})\s*```', raw_text, re.DOTALL)
    if match:
        json_text = match.group(1)
    else:
        start_index = raw_text.find('{')
        end_index = raw_text.rfind('}')
        if start_index != -1 and end_index != -1 and end_index > start_index:
            json_text = raw_text[start_index : end_index + 1]
        else:
            return None
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        return None

def generate_explanation(question_data):
    """Gemini를 사용하여 문제에 대한 상세한 해설을 생성합니다."""
    if not model: return {"error": "Gemini API가 설정되지 않았습니다."}

    question_text = question_data['question']
    try:
        options = json.loads(question_data['options'])
        options_str = "\n".join([f"{key}. {value}" for key, value in options.items()])
    except (json.JSONDecodeError, TypeError):
        options_str = "선택지를 불러오는 데 실패했습니다."
    try:
        answer = json.loads(question_data['answer'])
        if not isinstance(answer, list):
             answer = [str(answer)]
    except (json.JSONDecodeError, TypeError):
        answer = []

    # --- 여기가 빠져있던 핵심 부분입니다 ---
    # AI에게 보낼 질문(prompt)을 정의합니다.
    prompt = f"""
    You are an instructor known for making students feel confident and smart. Your name is 'Gemini Tutor'.
    Explain the following Oracle OCP question for a beginner. The correct answer is {answer}.
    Do not use overly complex jargon without explaining it first.

    **Question:**
    {question_text}
    
    **Options:**
    {options_str}

    Please structure your explanation in three distinct parts as a JSON object, using Korean:

    1.  "analogy": A simple, easy-to-understand analogy or metaphor for a non-technical person. (쉬운 비유)
    2.  "visualization": A text-based visualization. Describe how data moves or how structures relate using simple text diagrams or step-by-step descriptions. (텍스트 시각화)
    3.  "core_concepts": A clear summary of the key Oracle concepts being tested. Explain why the correct answer is right and why the other options are wrong. (핵심 개념 정리)

    **Output Format (Strictly follow this JSON format without any surrounding text or markdown):**
    {{
      "analogy": "...",
      "visualization": "...",
      "core_concepts": "..."
    }}
    """
    # --- 여기까지 ---

    try:
        response = model.generate_content(prompt, safety_settings=safety_settings)
        parsed_json = clean_and_parse_json(response.text)
        if parsed_json:
            return parsed_json
        else:
            return {"error": f"AI 응답에서 유효한 JSON을 파싱하는 데 실패했습니다. 원본 응답: {response.text}"}
    except exceptions.InternalServerError as e:
        return {"error": f"AI 서버 내부 오류(500)가 발생했습니다. 잠시 후 다시 시도해주세요. 원인: {e}"}
    except exceptions.ResourceExhausted as e:
        return {"error": f"API 사용량 한도를 초과했습니다. Google Cloud 콘솔에서 사용량을 확인해주세요. 원인: {e}"}
    except Exception as e:
        return {"error": f"해설 생성 중 예상치 못한 API 오류 발생: {e}"}

def generate_modified_question(original_question_data):
    """Gemini를 사용하여 기존 문제를 변형한 새로운 문제를 생성합니다."""
    if not model: return {"error": "Gemini API가 설정되지 않았습니다."}
    
    question_text = original_question_data['question']
    try:
        options = json.loads(original_question_data['options'])
        answer = json.loads(original_question_data['answer'])
    except (json.JSONDecodeError, TypeError):
        return {"error": "원본 문제 데이터의 형식이 잘못되었습니다."}

    options_str = "\n".join([f"{key}. {value}" for key, value in options.items()])
    
    prompt = f"""
    You are an expert Oracle DBA exam question creator.
    Based on the following Oracle OCP question, create a new, similar question.
    
    **Instructions:**
    - Test the exact same core concept.
    - Change details like table/column names, and values.
    - Rephrase the question and options.
    - The output MUST be a valid JSON object and nothing else.
    
    **Example:**
    **Original Input:**
    Question: Which query is valid for the EMPLOYEES table?
    Options: {{...}}
    Correct Answer: ["C"]
    
    **Your Expected Output (JSON only):**
    {{
      "question": "For the WORKERS table, which of the following SQL statements is correct?",
      "options": {{ "A": "...", "B": "...", "C": "...", "D": "...", "E": "..." }},
      "answer": ["B"]
    }}
    ---
    **Now, process the following real request:**
    **Original Question:**
    Question: {question_text}
    Options:
    {options_str}
    Correct Answer: {answer}

    **Your Output (JSON only):**
    """
    
    try:
        response = model.generate_content(prompt, safety_settings=safety_settings)
        parsed_json = clean_and_parse_json(response.text)
        
        if not parsed_json:
            return {"error": f"AI 응답에서 유효한 JSON을 파싱하는 데 실패했습니다. 원본 응답: {response.text}"}

        if not all(k in parsed_json for k in ['question', 'options', 'answer']):
            return {"error": "AI가 생성한 데이터에 필수 필드가 누락되었습니다."}
        if not isinstance(parsed_json.get('answer'), list):
             parsed_json['answer'] = [str(parsed_json.get('answer'))]

        return parsed_json
 
    except exceptions.InternalServerError as e:
        return {"error": f"AI 서버 내부 오류(500)가 발생했습니다. 잠시 후 다시 시도해주세요. 원인: {e}"}
    except exceptions.ResourceExhausted as e:
        return {"error": f"API 사용량 한도를 초과했습니다. Google Cloud 콘솔에서 사용량을 확인해주세요. 원인: {e}"}
    except Exception as e:
        return {"error": f"문제 변형 중 예상치 못한 API 오류 발생: {e}"}