# db_utils.py
"""
데이터베이스(SQLite)와의 모든 상호작용을 담당하는 함수들을 모아놓은 모듈.
이 파일은 테이블 생성, 데이터 CRUD(Create, Read, Update, Delete),
사용자 관리 및 통계 데이터 조회를 포함합니다.
"""
import sqlite3
import json
import pandas as pd

# --- 상수 정의 ---
DB_NAME = 'ocp_quiz.db'

# --- 데이터베이스 연결 ---
def get_db_connection():
    """
    데이터베이스 연결 객체를 생성하고 반환합니다.
    - check_same_thread=False: Streamlit의 멀티스레딩 환경에서 SQLite를 안전하게 사용하기 위한 설정.
    - row_factory=sqlite3.Row: 결과를 딕셔너리처럼 컬럼 이름으로 접근할 수 있게 해주는 설정.
    """
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# --- 스키마 설정 ---
def setup_database_tables():
    """
    앱에 필요한 모든 테이블(users, questions 등)을 생성하고,
    필요한 경우 기존 테이블의 스키마를 안전하게 업그레이드(ALTER)합니다.
    앱 시작 시 단 한 번만 호출되어야 합니다.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # --- users 테이블 스키마 ---
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(users)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'role' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
    else:
        cursor.execute('''
        CREATE TABLE users (
            username TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        )''')

    # --- original_questions 테이블 스키마 ---
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='original_questions'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(original_questions)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'media_url' not in columns:
            cursor.execute("ALTER TABLE original_questions ADD COLUMN media_url TEXT")
        if 'media_type' not in columns:
            cursor.execute("ALTER TABLE original_questions ADD COLUMN media_type TEXT")
    else:
        cursor.execute('''
        CREATE TABLE original_questions (
            id INTEGER PRIMARY KEY, question TEXT NOT NULL, options TEXT NOT NULL,
            answer TEXT NOT NULL, concept TEXT, media_url TEXT, media_type TEXT
        )''')

    # --- 기타 테이블 (IF NOT EXISTS로 간단히 생성) ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS modified_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, original_id INTEGER, question TEXT NOT NULL,
        options TEXT NOT NULL, answer TEXT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (original_id) REFERENCES original_questions (id)
    )''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, question_id INTEGER NOT NULL,
        question_type TEXT NOT NULL, user_choice TEXT NOT NULL, is_correct BOOLEAN NOT NULL,
        solved_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()
    print("모든 데이터베이스 테이블 확인/생성/업그레이드 완료.")

# --- 원본 문제 데이터 로딩 ---
def load_original_questions_from_json(json_path='questions_final.json'):
    """JSON 파일에서 원본 질문 데이터를 읽어 DB를 완전히 새로 고칩니다."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            questions = json.load(f)
    except FileNotFoundError:
        return 0, f"'{json_path}' 파일을 찾을 수 없습니다."

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM original_questions")
    
    for q in questions:
        cursor.execute(
            "INSERT INTO original_questions (id, question, options, answer) VALUES (?, ?, ?, ?)",
            (q.get('id'), q.get('question'), json.dumps(q.get('options', {})), json.dumps(q.get('answer', [])))
        )
    
    conn.commit()
    conn.close()
    return len(questions), None

# --- 문제 관리 (CRUD) ---
def get_all_question_ids(q_type='original'):
    """특정 타입의 모든 문제 ID 목록을 정렬하여 반환합니다."""
    # ... (이하 모든 함수의 내용은 이전과 동일하며, 주석만 정리되었습니다)
    table_name = 'original_questions' if q_type == 'original' else 'modified_questions'
    conn = get_db_connection()
    ids = [row['id'] for row in conn.execute(f"SELECT id FROM {table_name} ORDER BY id ASC").fetchall()]
    conn.close()
    return ids

def get_question_by_id(q_id, q_type='original'):
    """ID와 타입으로 특정 문제를 파이썬 딕셔너리 형태로 반환합니다."""
    table_name = 'original_questions' if q_type == 'original' else 'modified_questions'
    conn = get_db_connection()
    question_row = conn.execute(f"SELECT * FROM {table_name} WHERE id = ?", (q_id,)).fetchone()
    conn.close()
    return dict(question_row) if question_row else None

def add_new_original_question(question_text, options_dict, answer_list, media_url=None, media_type=None):
    """새로운 원본 문제를 DB에 추가하고 새 ID를 반환합니다."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT IFNULL(MAX(id), 0) + 1 FROM original_questions")
    new_id = cursor.fetchone()[0]
    cursor.execute(
        "INSERT INTO original_questions (id, question, options, answer, media_url, media_type) VALUES (?, ?, ?, ?, ?, ?)",
        (new_id, question_text, json.dumps(options_dict), json.dumps(answer_list), media_url, media_type)
    )
    conn.commit()
    conn.close()
    return new_id

def update_original_question(q_id, question_text, options_dict, answer_list, media_url=None, media_type=None):
    """ID를 기반으로 원본 문제의 내용을 업데이트합니다."""
    conn = get_db_connection()
    conn.execute(
        "UPDATE original_questions SET question = ?, options = ?, answer = ?, media_url = ?, media_type = ? WHERE id = ?",
        (question_text, json.dumps(options_dict), json.dumps(answer_list), media_url, media_type, q_id)
    )
    conn.commit()
    conn.close()

# --- 사용자 관리 ---
def fetch_all_users():
    """모든 사용자 정보를 streamlit-authenticator 형식으로 변환하여 반환합니다."""
    conn = get_db_connection()
    try:
        users = conn.execute("SELECT * FROM users").fetchall()
    except sqlite3.OperationalError:
        users = []
    conn.close()
    
    user_credentials = {"usernames": {}}
    for user in users:
        role = user['role'] if 'role' in user else 'user'
        user_credentials["usernames"][user['username']] = {
            "name": user['name'],
            "password": user['password'],
            "role": user.get('role', 'user')
        }
    return user_credentials

def add_new_user(username, name, hashed_password):
    """새로운 사용자를 'users' 테이블에 추가합니다. 역할(role)은 기본값 'user'로 설정됩니다."""
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO users (username, name, password) VALUES (?, ?, ?)", (username, name, hashed_password))
        conn.commit()
        return True, None
    except sqlite3.IntegrityError:
        return False, "이미 존재하는 사용자 이름입니다."
    finally:
        conn.close()

def delete_user(username):
    """특정 사용자와 해당 사용자의 모든 학습 기록을 삭제합니다."""
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM user_answers WHERE username = ?", (username,))
        conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()
    except Exception as e:
        print(f"사용자 삭제 중 오류 발생: {e}")
    finally:
        conn.close()

def get_all_users_for_admin():
    """관리자 페이지를 위해 모든 사용자 목록을 반환합니다 (비밀번호 제외)."""
    conn = get_db_connection()
    try:
        return conn.execute("SELECT username, name, role FROM users ORDER BY username ASC").fetchall()
    except Exception as e:
        print(f"모든 사용자 목록 조회 중 오류 발생: {e}")
        return []
    finally:
        conn.close()

def ensure_master_account(username, name, hashed_password):
    """마스터 계정을 생성하거나 'admin' 역할로 업데이트합니다."""
    conn = get_db_connection()
    conn.execute(
        "INSERT OR REPLACE INTO users (username, name, password, role) VALUES (?, ?, ?, ?)",
        (username, name, hashed_password, 'admin')
    )
    conn.commit()
    conn.close()

# --- 답변 기록 및 통계 ---
def save_user_answer(username, q_id, q_type, user_choice, is_correct):
    """특정 사용자의 답변 기록을 DB에 저장합니다."""
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO user_answers (username, question_id, question_type, user_choice, is_correct) VALUES (?, ?, ?, ?, ?)",
        (username, q_id, q_type, json.dumps(user_choice), is_correct)
    )
    conn.commit()
    conn.close()

def get_wrong_answers(username):
    """특정 사용자의 틀린 문제 목록을 가져옵니다."""
    conn = get_db_connection()
    wrong_answers = conn.execute(
        "SELECT DISTINCT question_id, question_type FROM user_answers WHERE is_correct = 0 AND username = ?", (username,)
    ).fetchall()
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
    """저장된 모든 AI 변형 문제를 가져옵니다."""
    conn = get_db_connection()
    return conn.execute("SELECT id, question FROM modified_questions ORDER BY id DESC").fetchall()

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