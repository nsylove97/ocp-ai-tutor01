import re
import json

def parse_ocp_file_revised(filepath):
    """
    복잡한 구조의 OCP 시험 문제 텍스트 파일을 파싱하여 JSON 구조로 변환합니다.
    - 여러 줄로 된 질문, 문제 앞 설명, 불규칙한 공백을 모두 처리합니다.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            content = file.read()
    except FileNotFoundError:
        print(f"오류: '{filepath}' 파일을 찾을 수 없습니다. 파일 이름과 경로를 확인해주세요.")
        return []

    # 파일 시작 부분에 인위적인 구분자를 추가하여 첫 문제도 동일한 패턴으로 처리
    content = "\nNO.0\n" + content
    
    # "NO.숫자" 패턴을 기준으로 전체 텍스트를 문제 블록으로 나눕니다.
    # 정규표현식의 'lookahead'((?=...))를 사용하여 구분자("NO.숫자")를 삭제하지 않고 유지합니다.
    problem_blocks = re.split(r'(?=\nNO\.\d+)', content)
    
    questions_data = []

    for block in problem_blocks:
        block = block.strip()
        if not block or not block.startswith("NO."):
            continue

        lines = block.split('\n')
        
        # 문제 번호 추출
        try:
            # NO.1 Which two... 와 같이 번호와 질문이 같은 줄에 있는 경우도 처리
            first_line_content = lines[0].split(maxsplit=1)
            question_number_str = first_line_content[0].replace('NO.', '').strip()
            question_number = int(question_number_str)
            
            # 첫 줄에 질문이 바로 이어지는 경우를 위해
            if len(first_line_content) > 1:
                lines[0] = first_line_content[1]
            else:
                lines.pop(0) # "NO.1" 라인 제거

        except (ValueError, IndexError):
            # NO.0 같은 인위적인 구분자는 건너뜁니다.
            continue
            
        question_text_parts = []
        options = {}
        found_options = False # 선택지 부분을 찾았는지 여부를 나타내는 플래그

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 선택지 패턴 (A. B. C. 등)을 더 정교하게 확인합니다.
            option_match = re.match(r'^([A-Z])\.\s+(.*)', line)
            
            if option_match:
                found_options = True # 이제부터는 선택지 부분임
                option_letter = option_match.group(1)
                option_text = option_match.group(2).strip()
                options[option_letter] = option_text
            elif not found_options:
                # 아직 선택지를 만나지 않았다면, 모든 내용은 질문의 일부입니다.
                question_text_parts.append(line)

        if question_text_parts and options:
            # 질문 부분을 합칠 때, 줄바꿈을 유지하여 코드 블록 등의 형식을 보존합니다.
            full_question_text = "\n".join(question_text_parts)
            
            questions_data.append({
                "id": question_number,
                "question": full_question_text,
                "options": options,
                "answer": [] # 정답은 여전히 비워둡니다.
            })
            
    return questions_data

# --- 스크립트 실행 부분 ---
if __name__ == "__main__":
    input_filename = '1z0-082.txt'
    output_filename = 'questions.json'

    # 개선된 파서 함수 호출
    parsed_questions = parse_ocp_file_revised(input_filename)

    if parsed_questions:
        # 파싱된 결과를 JSON 파일로 저장
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(parsed_questions, f, indent=4, ensure_ascii=False)

        print(f"총 {len(parsed_questions)}개의 문제를 성공적으로 파싱했습니다.")
        print(f"결과가 '{output_filename}' 파일에 저장되었습니다.")
        
        # 첫 번째 파싱된 문제 예시 출력
        print("\n--- 파싱 결과 예시 (첫 번째 문제) ---")
        print(json.dumps(parsed_questions[0], indent=2, ensure_ascii=False))
        print("------------------------------------")