import sqlite3
import os
import threading

# Use a specific path for the db
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "maas_auth.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role_id INTEGER NOT NULL,
        is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (role_id) REFERENCES roles(id)
    );
    """)

    # Seed roles
    roles_to_seed = ['admin', 'operator', 'viewer']
    for role in roles_to_seed:
        cursor.execute("INSERT OR IGNORE INTO roles (name) VALUES (?)", (role,))
        
    cursor.execute("SELECT id FROM roles WHERE name = 'admin'")
    admin_role = cursor.fetchone()
    if admin_role:
        admin_role_id = admin_role["id"]
        cursor.execute("SELECT id FROM users WHERE username = 'admin'")
        if not cursor.fetchone():
            from app.services.auth_service import get_password_hash
            default_password_hash = get_password_hash("admin")
            cursor.execute("""
                INSERT INTO users (username, password_hash, role_id)
                VALUES (?, ?, ?)
            """, ("admin", default_password_hash, admin_role_id))
            
    conn.commit()
    conn.close()

def get_user_by_username(username: str) -> sqlite3.Row:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.username, u.password_hash, u.is_active, r.name as role_name, r.id as role_id
            FROM users u
            JOIN roles r ON u.role_id = r.id
            WHERE u.username = ?
        """, (username,))
        return cursor.fetchone()
    finally:
        conn.close()

def get_user_by_id(user_id: int) -> sqlite3.Row:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.username, u.password_hash, u.is_active, r.name as role_name, r.id as role_id
            FROM users u
            JOIN roles r ON u.role_id = r.id
            WHERE u.id = ?
        """, (user_id,))
        return cursor.fetchone()
    finally:
        conn.close()

def get_role_by_name(role_name: str) -> sqlite3.Row:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM roles WHERE name = ?", (role_name,))
        return cursor.fetchone()
    finally:
        conn.close()

def create_user(username: str, password_hash: str, role_id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (username, password_hash, role_id)
            VALUES (?, ?, ?)
        """, (username, password_hash, role_id))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

# Initialize on import
def delete_user(username: str) -> bool:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def update_user_password(username: str, password_hash: str) -> bool:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users
            SET password_hash = ?
            WHERE username = ?
        """, (password_hash, username))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

init_db()
