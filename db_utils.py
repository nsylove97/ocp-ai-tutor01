# db_utils.py
"""
데이터베이스(SQLite)와의 모든 상호작용을 담당하는 함수들을 모아놓은 모듈.
"""
import sqlite3
import json
import pandas as pd

DB_NAME = 'ocp_quiz.db'

def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def setup_database_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    # users 테이블
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if not cursor.fetchone():
        cursor.execute('''CREATE TABLE users (username TEXT PRIMARY KEY, name TEXT NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user')''')
    else:
        cursor.execute("PRAGMA table_info(users)")
        if 'role' not in [col['name'] for col in cursor.fetchall()]:
            cursor.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
            
    # original_questions 테이블
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='original_questions'")
    table_exists = cursor.fetchone()
    if table_exists:
        cursor.execute("PRAGMA table_info(original_questions)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'media_url' not in columns: cursor.execute("ALTER TABLE original_questions ADD COLUMN media_url TEXT")
        if 'media_type' not in columns: cursor.execute("ALTER TABLE original_questions ADD COLUMN media_type TEXT")
        if 'difficulty' not in columns: cursor.execute("ALTER TABLE original_questions ADD COLUMN difficulty TEXT NOT NULL DEFAULT '보통'")
    else:
        cursor.execute('''
        CREATE TABLE original_questions (
            id INTEGER PRIMARY KEY, question TEXT NOT NULL, options TEXT NOT NULL,
            answer TEXT NOT NULL, concept TEXT, media_url TEXT, media_type TEXT,
            difficulty TEXT NOT NULL DEFAULT '보통'
        )''')
    
    # 기타 테이블
    cursor.execute('''CREATE TABLE IF NOT EXISTS modified_questions (...)''') # 스키마 생략
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_answers (...)''') # 스키마 생략
    conn.commit()
    conn.close()
    print("모든 DB 테이블 확인/생성/업그레이드 완료.")

def load_original_questions_from_json(questions_with_difficulty: list):
    """
    '난이도'가 이미 포함된 문제 데이터 리스트를 받아 DB를 새로 고칩니다.
    """
    if not questions_with_difficulty:
        return 0, "입력된 문제 데이터가 없습니다."

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM original_questions")
    
    for q in questions_with_difficulty:
        cursor.execute(
            """INSERT INTO original_questions 
               (id, question, options, answer, difficulty, media_url, media_type) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                q.get('id'), q.get('question'), json.dumps(q.get('options', {})),
                json.dumps(q.get('answer', [])), q.get('difficulty', '보통'),
                q.get('media_url'), q.get('media_type')
            )
        )
            
    conn.commit()
    conn.close()
    return len(questions_with_difficulty), None

def get_wrong_answers(username: str):
    """특정 사용자의 틀린 문제 목록(상세 정보 포함)을 가져옵니다."""
    conn = get_db_connection()
    query = """
    WITH all_questions AS (
        SELECT 'original' as type, id, question, options, answer, media_url, media_type, difficulty FROM original_questions
        UNION ALL
        SELECT 'modified' as type, id, question, options, answer, NULL as media_url, NULL as media_type, '보통' as difficulty FROM modified_questions
    )
    SELECT 
        ua.question_type, q.*
    FROM user_answers ua
    JOIN all_questions q ON ua.question_id = q.id AND ua.question_type = q.type
    WHERE ua.is_correct = 0 AND ua.username = ?
    GROUP BY ua.question_id, ua.question_type 
    ORDER BY MAX(ua.solved_at) DESC
    """
    wrong_answers = conn.execute(query, (username,)).fetchall()
    conn.close()
    return wrong_answers

def delete_wrong_answer(username, question_id, question_type):
    """특정 사용자의 특정 오답 기록을 삭제합니다."""
    conn = get_db_connection()
    conn.execute(
        "DELETE FROM user_answers WHERE question_id = ? AND question_type = ? AND username = ?",
        (question_id, question_type, username)
    )
    conn.commit()
    conn.close()

def get_stats(username):
    """특정 사용자의 전체 학습 통계를 계산하여 반환합니다."""
    conn = get_db_connection()
    try:
        df = pd.read_sql_query("SELECT is_correct FROM user_answers WHERE username = ?", conn, params=(username,))
        total = len(df)
        if total == 0: return 0, 0, 0.0
        correct = int(df['is_correct'].sum())
        accuracy = (correct / total) * 100
        return total, correct, accuracy
    except (pd.io.sql.DatabaseError, KeyError):
        return 0, 0, 0.0
    finally:
        conn.close()

def get_top_5_missed(username):
    """특정 사용자가 가장 많이 틀린 문제 Top 5를 DataFrame으로 반환합니다."""
    conn = get_db_connection()
    try:
        query = """
        SELECT q.id, q.question, COUNT(*) as wrong_count
        FROM user_answers ua
        JOIN original_questions q ON ua.question_id = q.id
        WHERE ua.is_correct = 0 AND ua.question_type = 'original' AND ua.username = ?
        GROUP BY q.id, q.question
        ORDER BY wrong_count DESC, q.id ASC
        LIMIT 5
        """
        return pd.read_sql_query(query, conn, params=(username,))
    except pd.io.sql.DatabaseError:
        return pd.DataFrame()
    finally:
        conn.close()

# --- AI 변형 문제 관리 ---
def get_all_modified_questions():
    """저장된 모든 AI 변형 문제의 상세 정보를 가져옵니다."""
    conn = get_db_connection()
    questions = conn.execute("SELECT * FROM modified_questions ORDER BY id DESC").fetchall()
    conn.close()
    return questions

def save_modified_question(original_id, q_data):
    """AI가 생성한 변형 문제를 저장하고 새 ID를 반환합니다."""
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

def delete_modified_question(question_id):
    """특정 AI 변형 문제와 관련된 모든 사용자의 오답 기록을 삭제합니다."""
    conn = get_db_connection()
    conn.execute("DELETE FROM user_answers WHERE question_id = ? AND question_type = 'modified'", (question_id,))
    conn.execute("DELETE FROM modified_questions WHERE id = ?", (question_id,))
    conn.commit()
    conn.close()

def clear_all_modified_questions():
    """모든 AI 변형 문제와 관련된 모든 사용자의 오답 기록을 삭제합니다."""
    conn = get_db_connection()
    conn.execute("DELETE FROM user_answers WHERE question_type = 'modified'")
    conn.execute("DELETE FROM modified_questions")
    conn.commit()
    conn.close()

def get_question_ids_by_difficulty(difficulty='모든 난이도'):
    """
    특정 난이도 또는 모든 난이도의 원본 문제 ID 목록을 반환합니다.
    """
    conn = get_db_connection()
    if difficulty == '모든 난이도':
        query = "SELECT id FROM original_questions ORDER BY id ASC"
        ids = [row['id'] for row in conn.execute(query).fetchall()]
    else:
        query = "SELECT id FROM original_questions WHERE difficulty = ? ORDER BY id ASC"
        ids = [row['id'] for row in conn.execute(query, (difficulty,)).fetchall()]
    conn.close()
    return ids

def get_all_question_ids(q_type='original'):
    """
    특정 타입('original' 또는 'modified')의 모든 문제 ID 목록을 반환합니다.
    'original'의 경우 get_question_ids_by_difficulty를 재활용합니다.
    """
    if q_type == 'original':
        # '모든 난이도' 옵션을 사용하여 모든 원본 문제 ID를 가져옴
        return get_question_ids_by_difficulty('모든 난이도')
    else:
        # 'modified'의 경우 기존 로직 유지
        conn = get_db_connection()
        ids = [row['id'] for row in conn.execute("SELECT id FROM modified_questions ORDER BY id ASC").fetchall()]
        conn.close()
        return ids

def clear_all_original_questions():
    """DB에서 모든 원본 문제를 삭제합니다."""
    conn = get_db_connection()
    # 원본 문제와 관련된 오답 기록도 함께 삭제하는 것이 좋습니다.
    conn.execute("DELETE FROM user_answers WHERE question_type = 'original'")
    conn.execute("DELETE FROM original_questions")
    conn.commit()
    conn.close()

def export_questions_to_json_format():
    """
    데이터베이스의 'original_questions' 테이블에 있는 모든 데이터를
    JSON 파일 형식(딕셔너리 리스트)으로 변환하여 반환합니다.
    """
    conn = get_db_connection()
    # "SELECT * ..."를 사용하여 모든 컬럼을 가져옵니다.
    all_questions_rows = conn.execute("SELECT * FROM original_questions ORDER BY id ASC").fetchall()
    conn.close()
    
    questions_list = []
    for row in all_questions_rows:
        # DB row 객체를 파이썬 딕셔너리로 변환
        question_dict = dict(row)
        
        # JSON으로 저장된 'options'와 'answer'를 다시 파이썬 객체로 파싱
        try:
            question_dict['options'] = json.loads(question_dict['options'])
        except (json.JSONDecodeError, TypeError):
            question_dict['options'] = {} # 파싱 실패 시 빈 딕셔너리
            
        try:
            question_dict['answer'] = json.loads(question_dict['answer'])
        except (json.JSONDecodeError, TypeError):
            question_dict['answer'] = [] # 파싱 실패 시 빈 리스트
            
        questions_list.append(question_dict)
        
    return questions_list