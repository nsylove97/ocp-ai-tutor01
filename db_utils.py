# db_utils.py
"""
데이터베이스(SQLite)와의 모든 상호작용을 담당하는 함수들을 모아놓은 모듈.
이 파일은 테이블 생성, 데이터 CRUD(Create, Read, Update, Delete),
사용자 관리 및 통계 데이터 조회를 포함합니다.
"""
# --- Python Standard Libraries ---
import sqlite3
import json

# --- 3rd Party Libraries ---
import pandas as pd

# --- 상수 정의 ---
DB_NAME = 'ocp_quiz.db'

# --- 데이터베이스 연결 ---
def get_db_connection():
    """데이터베이스 연결 객체를 생성하고 반환합니다."""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# --- 스키마 설정 ---
def setup_database_tables():
    """앱에 필요한 모든 테이블을 생성하고, 필요한 경우 스키마를 업그레이드합니다."""
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
    
    # AI 해설 저장 테이블
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS ai_explanations (
        question_id INTEGER NOT NULL,
        question_type TEXT NOT NULL,
        explanation TEXT NOT NULL, -- JSON 형태의 해설
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (question_id, question_type)
    )''')

     # AI 튜터 채팅 기록 저장 테이블
    cursor.execute("PRAGMA table_info(chat_history)")
    columns = [row['name'] for row in cursor.fetchall()]
    if 'session_title' not in columns:
        cursor.execute("ALTER TABLE chat_history ADD COLUMN session_title TEXT")

    # 기타 테이블
    cursor.execute('''CREATE TABLE IF NOT EXISTS modified_questions (id INTEGER PRIMARY KEY AUTOINCREMENT, original_id INTEGER, question TEXT, options TEXT, answer TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_answers (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, question_id INTEGER, question_type TEXT, user_choice TEXT, is_correct BOOLEAN, solved_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()
    print("모든 데이터베이스 테이블 확인/생성/업그레이드 완료.")

# --- 데이터 로딩/내보내기 ---
def load_original_questions_from_json(questions_with_difficulty: list):
    """'난이도'가 포함된 문제 리스트를 받아 DB를 새로 고칩니다."""
    if not questions_with_difficulty:
        return 0, "입력된 문제 데이터가 없습니다."
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM original_questions")
    for q in questions_with_difficulty:
        cursor.execute(
            "INSERT INTO original_questions (id, question, options, answer, difficulty, media_url, media_type) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (q.get('id'), q.get('question'), json.dumps(q.get('options', {})), json.dumps(q.get('answer', [])), q.get('difficulty', '보통'), q.get('media_url'), q.get('media_type'))
        )
    conn.commit()
    conn.close()
    return len(questions_with_difficulty), None

def export_questions_to_json_format():
    """DB의 모든 원본 문제를 JSON 파일 형식(dict 리스트)으로 변환하여 반환합니다."""
    conn = get_db_connection()
    all_rows = conn.execute("SELECT * FROM original_questions ORDER BY id ASC").fetchall()
    conn.close()
    questions_list = []
    for row in all_rows:
        q_dict = dict(row)
        try: q_dict['options'] = json.loads(q_dict['options'])
        except: q_dict['options'] = {}
        try: q_dict['answer'] = json.loads(q_dict['answer'])
        except: q_dict['answer'] = []
        questions_list.append(q_dict)
    return questions_list

# --- 문제 관리 (CRUD) ---
def get_question_ids_by_difficulty(difficulty='모든 난이도'):
    """특정 난이도의 원본 문제 ID 목록을 반환합니다."""
    conn = get_db_connection()
    if difficulty == '모든 난이도':
        ids = [row['id'] for row in conn.execute("SELECT id FROM original_questions ORDER BY id ASC").fetchall()]
    else:
        ids = [row['id'] for row in conn.execute("SELECT id FROM original_questions WHERE difficulty = ? ORDER BY id ASC", (difficulty,)).fetchall()]
    conn.close()
    return ids

def get_all_question_ids(q_type='original'):
    """'original' 또는 'modified' 타입의 모든 문제 ID 목록을 반환합니다."""
    if q_type == 'original':
        return get_question_ids_by_difficulty('모든 난이도')
    else:
        conn = get_db_connection()
        ids = [row['id'] for row in conn.execute("SELECT id FROM modified_questions ORDER BY id ASC").fetchall()]
        conn.close()
        return ids

def get_question_by_id(q_id, q_type='original'):
    """ID와 타입으로 특정 문제를 딕셔너리 형태로 반환합니다."""
    table_name = 'original_questions' if q_type == 'original' else 'modified_questions'
    conn = get_db_connection()
    row = conn.execute(f"SELECT * FROM {table_name} WHERE id = ?", (q_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def add_new_original_question(question_text, options_dict, answer_list, difficulty, media_url=None, media_type=None):
    """새로운 원본 문제를 DB에 추가하고 새 ID를 반환합니다."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT IFNULL(MAX(id), 0) + 1 FROM original_questions")
    new_id = cursor.fetchone()[0]
    cursor.execute(
        "INSERT INTO original_questions (id, question, options, answer, difficulty, media_url, media_type) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (new_id, question_text, json.dumps(options_dict), json.dumps(answer_list), difficulty, media_url, media_type)
    )
    conn.commit()
    conn.close()
    return new_id

def update_original_question(q_id, question_text, options_dict, answer_list, difficulty, media_url=None, media_type=None):
    """ID를 기반으로 원본 문제의 내용을 업데이트합니다."""
    conn = get_db_connection()
    conn.execute(
        "UPDATE original_questions SET question=?, options=?, answer=?, difficulty=?, media_url=?, media_type=? WHERE id=?",
        (question_text, json.dumps(options_dict), json.dumps(answer_list), difficulty, media_url, media_type, q_id)
    )
    conn.commit()
    conn.close()

def clear_all_original_questions():
    """DB에서 모든 원본 문제와 관련 오답 기록을 삭제합니다."""
    conn = get_db_connection()
    conn.execute("DELETE FROM user_answers WHERE question_type = 'original'")
    conn.execute("DELETE FROM original_questions")
    conn.commit()
    conn.close()

# --- 사용자 관리 ---
def fetch_all_users():
    """모든 사용자 정보를 Authenticator용과 추가 정보용으로 분리하여 반환합니다."""
    conn = get_db_connection()
    users = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    credentials = {"usernames": {}}
    all_user_info = {}
    for user in users:
        username = user['username']
        credentials["usernames"][username] = {
            "name": user['name'],
            "password": user['password']
        }              
        role = user['role'] if 'role' in user.keys() else 'user'     
        all_user_info[username] = {
            "name": user['name'],
            "role": role,
            "password": user['password']
        }
    return credentials, all_user_info

def add_new_user(username, name, hashed_password):
    """새로운 사용자를 추가합니다."""
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO users (username, name, password) VALUES (?, ?, ?)", (username, name, hashed_password))
        conn.commit()
        return True, None
    except sqlite3.IntegrityError:
        return False, "이미 존재하는 아이디입니다."
    finally: conn.close()

def delete_user(username):
    """특정 사용자와 관련 학습 기록을 모두 삭제합니다."""
    conn = get_db_connection()
    conn.execute("DELETE FROM user_answers WHERE username = ?", (username,))
    conn.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    conn.close()

def get_all_users_for_admin():
    """관리자용으로 모든 사용자 목록을 반환합니다."""
    conn = get_db_connection()
    users = conn.execute("SELECT username, name, role FROM users ORDER BY username ASC").fetchall()
    conn.close()
    return users

def ensure_master_account(username, name, hashed_password):
    """마스터 관리자 계정이 존재하도록 보장합니다."""
    conn = get_db_connection()
    conn.execute("INSERT OR REPLACE INTO users (username, name, password, role) VALUES (?, ?, ?, ?)", (username, name, hashed_password, 'admin'))
    conn.commit()
    conn.close()

# --- 답변 기록 및 통계 ---
def save_user_answer(username, q_id, q_type, user_choice, is_correct):
    """사용자의 답변 기록을 저장합니다."""
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO user_answers (username, question_id, question_type, user_choice, is_correct) VALUES (?, ?, ?, ?, ?)",
        (username, q_id, q_type, json.dumps(user_choice), is_correct)
    )
    conn.commit()
    conn.close()

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
    conn.execute("DELETE FROM user_answers WHERE question_id = ? AND question_type = ? AND username = ?", (question_id, question_type, username))
    conn.commit()
    conn.close()

def get_stats(username):
    """특정 사용자의 학습 통계를 계산하여 반환합니다."""
    conn = get_db_connection()
    try:
        df = pd.read_sql_query("SELECT is_correct FROM user_answers WHERE username = ?", conn, params=(username,))
        total = len(df)
        if total == 0: return 0, 0, 0.0
        correct = int(df['is_correct'].sum())
        accuracy = (correct / total) * 100
        return total, correct, accuracy
    except: return 0, 0, 0.0
    finally: conn.close()

def get_top_5_missed(username):
    """특정 사용자가 가장 많이 틀린 문제 Top 5를 DataFrame으로 반환합니다."""
    conn = get_db_connection()
    try:
        query = """
        SELECT q.id, q.question, COUNT(*) as wrong_count
        FROM user_answers ua JOIN original_questions q ON ua.question_id = q.id
        WHERE ua.is_correct = 0 AND ua.question_type = 'original' AND ua.username = ?
        GROUP BY q.id, q.question ORDER BY wrong_count DESC, q.id ASC LIMIT 5
        """
        return pd.read_sql_query(query, conn, params=(username,))
    except: return pd.DataFrame()
    finally: conn.close()

# --- AI 변형 문제 관리 ---
def get_all_modified_questions():
    """모든 AI 변형 문제의 상세 정보를 가져옵니다."""
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
    """특정 AI 변형 문제와 관련 오답 기록을 삭제합니다."""
    conn = get_db_connection()
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

# --- AI 해설 관리 ---
def save_ai_explanation(q_id, q_type, explanation_json):
    """생성된 AI 해설을 DB에 저장하거나 업데이트합니다."""
    conn = get_db_connection()
    conn.execute(
        "INSERT OR REPLACE INTO ai_explanations (question_id, question_type, explanation) VALUES (?, ?, ?)",
        (q_id, q_type, explanation_json)
    )
    conn.commit()
    conn.close()

def get_ai_explanation_from_db(q_id, q_type):
    """DB에서 저장된 AI 해설을 가져옵니다."""
    conn = get_db_connection()
    row = conn.execute(
        "SELECT explanation FROM ai_explanations WHERE question_id = ? AND question_type = ?",
        (q_id, q_type)
    ).fetchone()
    conn.close()
    return json.loads(row['explanation']) if row else None

def delete_ai_explanation(q_id, q_type):
    """DB에서 특정 AI 해설을 삭제합니다."""
    conn = get_db_connection()
    conn.execute("DELETE FROM ai_explanations WHERE question_id = ? AND question_type = ?", (q_id, q_type))
    conn.commit()
    conn.close()

def get_all_explanations_for_admin():
    """관리자용으로 저장된 모든 AI 해설 목록을 가져옵니다."""
    conn = get_db_connection()
    rows = conn.execute("SELECT question_id, question_type FROM ai_explanations ORDER BY question_id").fetchall()
    conn.close()
    return rows

# --- AI 튜터 채팅 기록 관리 ---
def get_chat_history(username, session_id):
    """특정 사용자의 특정 채팅 세션 기록을 가져옵니다."""
    conn = get_db_connection()
    history = conn.execute(
        "SELECT role, content FROM chat_history WHERE username = ? AND session_id = ? ORDER BY timestamp ASC",
        (username, session_id)
    ).fetchall()
    conn.close()
    return [{"role": row['role'], "parts": [row['content']]} for row in history]

def save_chat_message(username, session_id, role, content):
    """채팅 메시지를 DB에 저장합니다."""
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO chat_history (username, session_id, role, content) VALUES (?, ?, ?, ?)",
        (username, session_id, role, content)
    )
    conn.commit()
    conn.close()

def get_chat_sessions(username):
    """특정 사용자의 모든 채팅 세션 ID와 첫 메시지를 가져옵니다."""
    conn = get_db_connection()
    query = """
    SELECT session_id, session_title, content
    FROM chat_history
    WHERE id IN (
        SELECT MIN(id)
        FROM chat_history
        WHERE username = ?
        GROUP BY session_id
    )
    ORDER BY timestamp DESC
    """
    sessions = conn.execute(query, (username,)).fetchall()
    conn.close()
    return sessions

def delete_chat_session(username, session_id):
    """특정 채팅 세션을 삭제합니다."""
    conn = get_db_connection()
    conn.execute("DELETE FROM chat_history WHERE username = ? AND session_id = ?", (username, session_id))
    conn.commit()
    conn.close()

def update_chat_session_title(username, session_id, new_title):
    """채팅 세션의 제목을 변경합니다."""
    conn = get_db_connection()
    conn.execute(
        "UPDATE chat_history SET session_title = ? WHERE username = ? AND session_id = ?",
        (new_title, username, session_id)
    )
    conn.commit()
    conn.close()

def get_full_chat_history(username, session_id):
    """
    메시지별 편집/삭제를 위해 id를 포함한 전체 채팅 기록을 가져옵니다.
    """
    conn = get_db_connection()
    history = conn.execute(
        "SELECT id, role, content FROM chat_history WHERE username = ? AND session_id = ? ORDER BY timestamp ASC",
        (username, session_id)
    ).fetchall()
    conn.close()
    return history

def update_chat_message(message_id, new_content):
    """특정 채팅 메시지의 내용을 수정합니다."""
    conn = get_db_connection()
    conn.execute("UPDATE chat_history SET content = ? WHERE id = ?", (new_content, message_id))
    conn.commit()
    conn.close()

def delete_chat_message_and_following(message_id, username, session_id):
    """
    특정 메시지와 그 이후의 모든 메시지를 삭제합니다.
    (사용자 질문을 수정하면, 그에 대한 AI 답변도 다시 받아야 하므로)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    # 1. 삭제할 메시지의 타임스탬프 가져오기
    cursor.execute("SELECT timestamp FROM chat_history WHERE id = ?", (message_id,))
    timestamp_row = cursor.fetchone()
    if not timestamp_row:
        conn.close()
        return

    # 2. 해당 타임스탬프 이후의 모든 메시지 삭제
    timestamp_to_delete_from = timestamp_row['timestamp']
    cursor.execute(
        "DELETE FROM chat_history WHERE username = ? AND session_id = ? AND timestamp >= ?",
        (username, session_id, timestamp_to_delete_from)
    )
    conn.commit()
    conn.close()

def delete_single_chat_message(message_id):
    """ID를 기반으로 정확히 하나의 채팅 메시지를 삭제합니다."""
    conn = get_db_connection()
    conn.execute("DELETE FROM chat_history WHERE id = ?", (message_id,))
    conn.commit()
    conn.close()