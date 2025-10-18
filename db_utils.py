# db_utils.py
import sqlite3
import json

DB_NAME = 'ocp_quiz.db'

def get_db_connection():
    """데이터베이스 연결을 생성하고 반환합니다."""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_all_question_ids(q_type='original'):
    """특정 타입의 모든 문제 ID 목록을 반환합니다."""
    table_name = 'original_questions' if q_type == 'original' else 'modified_questions'
    conn = get_db_connection()
    ids = [row['id'] for row in conn.execute(f"SELECT id FROM {table_name}").fetchall()]
    conn.close()
    return ids

def get_question_by_id(q_id, q_type='original'):
    """ID와 타입으로 특정 문제를 가져옵니다."""
    table_name = 'original_questions' if q_type == 'original' else 'modified_questions'
    conn = get_db_connection()
    question_data = conn.execute(f"SELECT * FROM {table_name} WHERE id = ?", (q_id,)).fetchone()
    conn.close()
    return question_data

def save_user_answer(q_id, q_type, user_choice, is_correct):
    """사용자의 오답 기록을 DB에 저장합니다."""
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO user_answers (question_id, question_type, user_choice, is_correct) VALUES (?, ?, ?, ?)",
        (q_id, q_type, json.dumps(user_choice), is_correct)
    )
    conn.commit()
    conn.close()

def get_wrong_answers():
    """틀린 문제 목록을 DB에서 가져옵니다."""
    conn = get_db_connection()
    wrong_answers = conn.execute(
        "SELECT DISTINCT question_id, question_type FROM user_answers WHERE is_correct = 0"
    ).fetchall()
    conn.close()
    return wrong_answers

def save_modified_question(original_id, q_data):
    """AI가 생성한 변형 문제를 DB에 저장하고 새 ID를 반환합니다."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO modified_questions (original_id, question, options, answer) VALUES (?, ?, ?, ?)",
        (original_id, q_data['question'], json.dumps(q_data['options']), json.dumps(q_data['answer']))
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id

def get_all_modified_questions():
    """저장된 모든 AI 변형 문제를 가져옵니다."""
    conn = get_db_connection()
    questions = conn.execute("SELECT id, question FROM modified_questions ORDER BY id DESC").fetchall()
    conn.close()
    return questions

def delete_wrong_answer(question_id, question_type):
    """특정 오답 기록을 user_answers 테이블에서 삭제합니다."""
    conn = get_db_connection()
    conn.execute(
        "DELETE FROM user_answers WHERE question_id = ? AND question_type = ?",
        (question_id, question_type)
    )
    conn.commit()
    conn.close()

def delete_modified_question(question_id):
    """특정 AI 변형 문제를 삭제합니다."""
    conn = get_db_connection()
    # 이 문제에 대한 오답 기록도 함께 삭제하는 것이 좋습니다 (데이터 정합성)
    conn.execute("DELETE FROM user_answers WHERE question_id = ? AND question_type = 'modified'", (question_id,))
    conn.execute("DELETE FROM modified_questions WHERE id = ?", (question_id,))
    conn.commit()
    conn.close()

def clear_all_modified_questions():
    """모든 AI 변형 문제와 관련 오답 기록을 삭제합니다."""
    conn = get_db_connection()
    conn.execute("DELETE FROM user_answers WHERE question_type = 'modified'")
    conn.execute("DELETE FROM modified_questions")
    conn.commit()
    conn.close()

import pandas as pd

def get_stats():
    """전체 학습 통계를 반환합니다."""
    conn = get_db_connection()
    # user_answers 테이블이 비어있을 경우를 대비
    try:
        df = pd.read_sql_query("SELECT is_correct FROM user_answers", conn)
        total_attempts = len(df)
        if total_attempts == 0:
            return 0, 0, 0.0
        correct_answers = df['is_correct'].sum()
        accuracy = (correct_answers / total_attempts) * 100 if total_attempts > 0 else 0
        return total_attempts, correct_answers, accuracy
    except pd.io.sql.DatabaseError: # 테이블이 아직 없을 경우
        return 0, 0, 0.0
    finally:
        conn.close()

def get_top_5_missed():
    """가장 많이 틀린 문제 Top 5를 반환합니다."""
    conn = get_db_connection()
    try:
        query = """
        SELECT q.id, q.question, COUNT(*) as wrong_count
        FROM user_answers ua
        JOIN original_questions q ON ua.question_id = q.id
        WHERE ua.is_correct = 0 AND ua.question_type = 'original'
        GROUP BY q.id, q.question
        ORDER BY wrong_count DESC
        LIMIT 5
        """
        df = pd.read_sql_query(query, conn)
        return df
    except pd.io.sql.DatabaseError:
        return pd.DataFrame() # 빈 데이터프레임 반환
    finally:
        conn.close()

def setup_database_tables():
    """
    앱에 필요한 모든 테이블을 생성합니다. (기존 db_setup.py의 create_tables 역할)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 원본 문제 테이블
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS original_questions (
        id INTEGER PRIMARY KEY, question TEXT NOT NULL, options TEXT NOT NULL,
        answer TEXT NOT NULL, concept TEXT
    )''')
    # 변형 문제 테이블
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS modified_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, original_id INTEGER, question TEXT NOT NULL,
        options TEXT NOT NULL, answer TEXT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (original_id) REFERENCES original_questions (id)
    )''')
    # 사용자 답변 기록 테이블
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, question_id INTEGER NOT NULL,
        question_type TEXT NOT NULL, user_choice TEXT NOT NULL,
        is_correct BOOLEAN NOT NULL, solved_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()
    print("데이터베이스 테이블 확인/생성 완료.")

def load_original_questions_from_json(json_path='questions_final.json'):
    """
    JSON 파일에서 원본 질문 데이터를 읽어 DB에 삽입합니다.
    기존 데이터를 모두 삭제하고 새로 로드합니다.
    (기존 db_setup.py의 load_questions_from_json 역할)
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            questions = json.load(f)
    except FileNotFoundError:
        print(f"오류: '{json_path}' 파일을 찾을 수 없습니다.")
        return 0, f"'{json_path}' 파일을 찾을 수 없습니다."

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 기존 데이터 삭제
    cursor.execute("DELETE FROM original_questions")
    
    # 새 데이터 삽입
    for q in questions:
        options_str = json.dumps(q.get('options', {}))
        answer_str = json.dumps(q.get('answer', []))
        cursor.execute(
            "INSERT INTO original_questions (id, question, options, answer) VALUES (?, ?, ?, ?)",
            (q['id'], q['question'], options_str, answer_str)
        )
    
    conn.commit()
    conn.close()
    print(f"'{json_path}' 파일로부터 총 {len(questions)}개의 문제를 DB에 로드했습니다.")
    return len(questions), None # 성공 시 로드된 문제 수와 에러 없음(None)을 반환

def update_original_question(q_id, question_text, options_dict, answer_list):
    """ID를 기반으로 원본 문제의 내용을 업데이트합니다."""
    conn = get_db_connection()
    
    # 딕셔너리와 리스트를 DB에 저장하기 위해 JSON 문자열로 변환
    options_str = json.dumps(options_dict)
    answer_str = json.dumps(answer_list)
    
    conn.execute(
        "UPDATE original_questions SET question = ?, options = ?, answer = ? WHERE id = ?",
        (question_text, options_str, answer_str, q_id)
    )
    conn.commit()
    conn.close()
