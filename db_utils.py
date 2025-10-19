# db_utils.py
"""
데이터베이스(SQLite)와의 모든 상호작용을 담당하는 함수들을 모아놓은 모듈.
CRUD(Create, Read, Update, Delete) 작업을 수행합니다.
"""
import sqlite3
import json
import pandas as pd

# --- Constants ---
DB_NAME = 'ocp_quiz.db'

# --- Connection ---
def get_db_connection():
    """데이터베이스 연결 객체를 생성하고 반환합니다."""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# --- Schema Setup ---
def setup_database_tables():
    """
    앱에 필요한 모든 테이블을 생성하고, 필요한 경우 스키마를 업그레이드합니다.
    앱 시작 시 호출되어 DB 구조의 일관성을 보장합니다.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # --- original_questions 테이블 스키마 확인 및 업그레이드 ---
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='original_questions'")
    table_exists = cursor.fetchone()

    if table_exists:
        cursor.execute("PRAGMA table_info(original_questions)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'media_url' not in columns:
            cursor.execute("ALTER TABLE original_questions ADD COLUMN media_url TEXT")
        if 'media_type' not in columns:
            cursor.execute("ALTER TABLE original_questions ADD COLUMN media_type TEXT")
    else:
        cursor.execute('''
        CREATE TABLE original_questions (
            id INTEGER PRIMARY KEY,
            question TEXT NOT NULL,
            options TEXT NOT NULL,
            answer TEXT NOT NULL,
            concept TEXT,
            media_url TEXT,
            media_type TEXT
        )''')

    # --- 다른 테이블들은 존재 여부만 확인하고 생성 ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS modified_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        original_id INTEGER,
        question TEXT NOT NULL,
        options TEXT NOT NULL,
        answer TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (original_id) REFERENCES original_questions (id)
    )''')
    # --- user_answers 테이블 스키마 확인 및 업그레이드 (핵심 수정) ---
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_answers'")
    table_exists = cursor.fetchone()

    if table_exists:
        cursor.execute("PRAGMA table_info(user_answers)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'username' not in columns:
            cursor.execute("ALTER TABLE user_answers ADD COLUMN username TEXT NOT NULL DEFAULT 'default_user'")
    else:
        cursor.execute('''
        CREATE TABLE user_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL, -- 사용자 식별을 위한 컬럼 추가
            question_id INTEGER NOT NULL,
            question_type TEXT NOT NULL,
            user_choice TEXT NOT NULL,
            is_correct BOOLEAN NOT NULL,
            solved_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

    conn.commit()
    conn.close()
    print("데이터베이스 테이블 확인/생성/업그레이드 완료.")

# --- Data Loading ---
def load_original_questions_from_json(json_path='questions_final.json'):
    """
    JSON 파일에서 원본 질문 데이터를 읽어 DB를 완전히 새로 고칩니다.

    Returns:
        tuple: (로드된 문제 수, 에러 메시지)
    """
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
            (q['id'], q['question'], json.dumps(q.get('options', {})), json.dumps(q.get('answer', [])))
        )
    
    conn.commit()
    loaded_count = cursor.rowcount
    conn.close()
    return len(questions), None

# --- Question Management (CRUD) ---
def get_all_question_ids(q_type='original'):
    """특정 타입의 모든 문제 ID 목록을 정렬하여 반환합니다."""
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
        """INSERT INTO original_questions 
           (id, question, options, answer, media_url, media_type) 
           VALUES (?, ?, ?, ?, ?, ?)""",
        (new_id, question_text, json.dumps(options_dict), json.dumps(answer_list), media_url, media_type)
    )
    conn.commit()
    conn.close()
    return new_id

def update_original_question(q_id, question_text, options_dict, answer_list, media_url=None, media_type=None):
    """ID를 기반으로 원본 문제의 내용을 업데이트합니다."""
    conn = get_db_connection()
    conn.execute(
        """UPDATE original_questions 
           SET question = ?, options = ?, answer = ?, media_url = ?, media_type = ? 
           WHERE id = ?""",
        (question_text, json.dumps(options_dict), json.dumps(answer_list), media_url, media_type, q_id)
    )
    conn.commit()
    conn.close()

# --- Answer & Analytics ---
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
    """특정 사용자의 틀린 문제 목록을 DB에서 가져옵니다."""
    conn = get_db_connection()
    wrong_answers = conn.execute(
        "SELECT DISTINCT question_id, question_type FROM user_answers WHERE is_correct = 0 AND username = ?",
        (username,)
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
    """특정 사용자의 전체 학습 통계를 반환합니다."""
    conn = get_db_connection()
    try:
        df = pd.read_sql_query("SELECT is_correct FROM user_answers WHERE username = ?", conn, params=(username,))
        total_attempts = len(df)
        if total_attempts == 0: return 0, 0, 0.0
        correct_answers = int(df['is_correct'].sum())
        accuracy = (correct_answers / total_attempts) * 100
        return total_attempts, correct_answers, accuracy
    except (pd.io.sql.DatabaseError, KeyError):
        return 0, 0, 0.0
    finally:
        conn.close()

def get_top_5_missed():
    """가장 많이 틀린 문제 Top 5를 DataFrame으로 반환합니다."""
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
        return pd.read_sql_query(query, conn)
    except pd.io.sql.DatabaseError:
        return pd.DataFrame()
    finally:
        conn.close()

# --- Modified Question Management ---
def get_all_modified_questions():
    """저장된 모든 AI 변형 문제를 가져옵니다."""
    conn = get_db_connection()
    questions = conn.execute("SELECT id, question FROM modified_questions ORDER BY id DESC").fetchall()
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
    """특정 AI 변형 문제를 삭제할 때, 모든 사용자의 관련 오답 기록도 함께 삭제합니다."""
    conn = get_db_connection()
    # username 조건 없이 해당 문제를 푼 모든 사용자의 기록을 삭제
    conn.execute("DELETE FROM user_answers WHERE question_id = ? AND question_type = 'modified'", (question_id,))
    conn.execute("DELETE FROM modified_questions WHERE id = ?", (question_id,))
    conn.commit()
    conn.close()

def clear_all_modified_questions():
    """모든 AI 변형 문제를 삭제할 때, 모든 사용자의 관련 오답 기록도 함께 삭제합니다."""
    conn = get_db_connection()
    # username 조건 없이 모든 사용자의 'modified' 타입 기록을 삭제
    conn.execute("DELETE FROM user_answers WHERE question_type = 'modified'")
    conn.execute("DELETE FROM modified_questions")
    conn.commit()
    conn.close()

def add_user_table():
    """'users' 테이블이 없으면 생성하고, 'role' 컬럼이 없으면 추가합니다."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 테이블 존재 여부 확인
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    table_exists = cursor.fetchone()

    if table_exists:
        # 테이블이 존재하면, 'role' 컬럼 존재 여부 확인
        cursor.execute("PRAGMA table_info(users)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'role' not in columns:
            # role 컬럼 추가. 기본값은 'user'
            cursor.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
    else:
        # 테이블이 없으면 새로 생성
        cursor.execute('''
        CREATE TABLE users (
            username TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user' -- 'user' 또는 'admin'
        )''')
        
    conn.commit()
    conn.close()
    print("사용자(users) 테이블 확인/생성/업그레이드 완료.")

def fetch_all_users():
    """모든 사용자 정보를 가져옵니다."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    conn.close()
    
    # streamlit-authenticator가 요구하는 형식으로 변환
    user_credentials = {"usernames": {}}
    for user in users:
        user_credentials["usernames"][user['username']] = {
            "name": user['name'],
            "password": user['password']
        }
    return user_credentials

def add_new_user(username, name, hashed_password):
    """새로운 사용자를 DB에 추가합니다."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, name, password) VALUES (?, ?, ?)",
            (username, name, hashed_password)
        )
        conn.commit()
        conn.close()
        return True, None # 성공
    except sqlite3.IntegrityError:
        conn.close()
        return False, "이미 존재하는 사용자 이름입니다." # 실패 (중복)
    
    # --- User Management Functions ---

def add_user_table():
    """
    'users' 테이블이 데이터베이스에 존재하지 않으면 새로 생성합니다.
    앱 시작 시 호출되어 사용자 관리의 기반을 마련합니다.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        password TEXT NOT NULL
    )''')
    conn.commit()
    conn.close()
    print("사용자(users) 테이블 확인/생성 완료.")


def fetch_all_users():
    """
    'users' 테이블에서 모든 사용자 정보를 가져와 
    streamlit-authenticator가 요구하는 딕셔너리 형식으로 변환하여 반환합니다.
    """
    conn = get_db_connection()
    # add_user_table()을 여기서 한번 더 호출하여 테이블 존재를 보장할 수 있습니다.
    add_user_table() 
    
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()
    except sqlite3.OperationalError:
        # users 테이블이 없는 예외적인 경우
        users = []
    conn.close()
    
    # streamlit-authenticator 라이브러리가 사용하는 특정 데이터 구조로 변환
    user_credentials = {"usernames": {}}
    for user in users:
        user_credentials["usernames"][user['username']] = {
            "name": user['name'],
            "password": user['password']
        }
    return user_credentials


def add_new_user(username, name, hashed_password):
    """
    새로운 사용자 정보를 'users' 테이블에 추가합니다.

    Returns:
        tuple: (성공 여부(bool), 메시지(str or None))
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # PRIMARY KEY 제약조건 덕분에 username이 중복되면 IntegrityError 발생
        cursor.execute(
            "INSERT INTO users (username, name, password) VALUES (?, ?, ?)",
            (username, name, hashed_password)
        )
        conn.commit()
        success = True
        message = None
    except sqlite3.IntegrityError:
        # 사용자 이름이 중복될 때 발생하는 오류
        success = False
        message = "이미 존재하는 사용자 이름입니다. 다른 이름을 사용해주세요."
    finally:
        conn.close()
        
    return success, message

def delete_user(username):
    """
    특정 사용자를 'users' 테이블에서 삭제합니다.
    해당 사용자의 모든 학습 기록('user_answers')도 함께 삭제하여 데이터 정합성을 유지합니다.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. 해당 사용자의 모든 답변 기록 삭제
        cursor.execute("DELETE FROM user_answers WHERE username = ?", (username,))
        
        # 2. 사용자 정보 삭제
        cursor.execute("DELETE FROM users WHERE username = ?", (username,))
        
        conn.commit()
        print(f"사용자 '{username}' 및 관련 데이터 삭제 완료.")
    except Exception as e:
        print(f"사용자 삭제 중 오류 발생: {e}")
    finally:
        conn.close()

def get_all_users_for_admin():
    """
    관리자 페이지를 위해 모든 사용자 목록을 가져옵니다 (비밀번호 제외).
    사용자 이름(username)을 기준으로 오름차순 정렬합니다.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT username, name, role FROM users ORDER BY username ASC")
        users = cursor.fetchall()
        return users
    except Exception as e:
        print(f"모든 사용자 목록 조회 중 오류 발생: {e}")
        return [] # 오류 발생 시 빈 리스트 반환
    finally:
        conn.close()