import sqlite3
import json

DB_NAME = 'ocp_quiz.db'

def create_tables(cursor):
    """
    프로그램에 필요한 테이블들을 생성합니다.
    """
    # 1. 원본 문제 테이블
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS original_questions (
        id INTEGER PRIMARY KEY,
        question TEXT NOT NULL,
        options TEXT NOT NULL, -- JSON 텍스트로 저장
        answer TEXT NOT NULL,  -- JSON 텍스트로 저장
        concept TEXT
    )
    ''')

    # 2. 변형 문제 테이블
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS modified_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        original_id INTEGER,
        question TEXT NOT NULL,
        options TEXT NOT NULL,
        answer TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (original_id) REFERENCES original_questions (id)
    )
    ''')
    
    # 3. 사용자 답변 기록 테이블
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER NOT NULL,
        question_type TEXT NOT NULL, -- 'original' 또는 'modified'
        user_choice TEXT NOT NULL,
        is_correct BOOLEAN NOT NULL,
        solved_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    print("테이블 생성 또는 확인 완료.")


def load_questions_from_json(cursor, json_path):
    """
    JSON 파일에서 질문 데이터를 읽어 DB에 삽입합니다.
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        questions = json.load(f)

    # 기존 데이터가 있다면 중복 삽입을 방지하기 위해 모두 삭제
    cursor.execute("DELETE FROM original_questions")
    print("기존 원본 문제 데이터를 삭제했습니다.")

    for q in questions:
        # 딕셔너리 형태의 options와 answer를 JSON 문자열로 변환하여 저장
        options_str = json.dumps(q['options'])
        answer_str = json.dumps(q['answer'])

        # 파라미터화된 쿼리를 사용하여 SQL 인젝션 방지
        cursor.execute(
            "INSERT INTO original_questions (id, question, options, answer) VALUES (?, ?, ?, ?)",
            (q['id'], q['question'], options_str, answer_str)
        )
    
    print(f"'{json_path}' 파일로부터 총 {len(questions)}개의 문제를 DB에 삽입했습니다.")


# --- 스크립트 실행 부분 ---
if __name__ == "__main__":
    # 1. 데이터베이스 연결 (파일이 없으면 새로 생성됨)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # 2. 테이블 생성
    create_tables(cursor)

    # 3. JSON 파일에서 데이터 로드하여 DB에 삽입
    load_questions_from_json(cursor, 'questions_final.json')

    # 4. 변경사항 저장 및 연결 종료
    conn.commit()
    conn.close()

    print(f"데이터베이스 설정 및 데이터 로딩이 '{DB_NAME}' 파일에 완료되었습니다.")