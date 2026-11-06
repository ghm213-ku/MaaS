import pytest
from fastapi.testclient import TestClient
from app.db.database import get_db_connection
from app.services.auth_service import get_password_hash, create_access_token
from main import app
import uuid
import jwt
from app.services.auth_service import JWT_SECRET, ALGORITHM

client = TestClient(app)

@pytest.fixture(scope="module")
def admin_token():
    # Insert an admin user into the DB
    username = f"admin_{uuid.uuid4()}"
    password = "adminpassword123"
    role_id = 1 # admin
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (username, password_hash, role_id)
        VALUES (?, ?, ?)
    """, (username, get_password_hash(password), role_id))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    token = create_access_token(user_id, "admin")
    yield token

    # Remove the user this fixture created
    conn = get_db_connection()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

def test_login_success():
    username = f"user_{uuid.uuid4()}"
    password = "mypassword"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (username, password_hash, role_id)
        VALUES (?, ?, ?)
    """, (username, get_password_hash(password), 2)) # operator
    conn.commit()
    conn.close()
    
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    assert "token" in response.json()
    assert response.json()["expires_in"] == 43200

def test_login_invalid_password():
    username = f"user_{uuid.uuid4()}"
    password = "mypassword"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (username, password_hash, role_id)
        VALUES (?, ?, ?)
    """, (username, get_password_hash(password), 2))
    conn.commit()
    conn.close()
    
    response = client.post("/auth/login", json={"username": username, "password": "wrongpassword"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"

def test_create_user_success(admin_token):
    username = f"newuser_{uuid.uuid4()}"
    
    response = client.post(
        "/auth/users", 
        json={"username": username, "role_id": 2},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 201
    assert "user_id" in response.json()

def test_create_user_forbidden():
    username = f"newuser_{uuid.uuid4()}"
    
    # Try with operator token
    op_token = create_access_token(user_id=1, role="operator")
    response = client.post(
        "/auth/users", 
        json={"username": username, "role_id": 2},
        headers={"Authorization": f"Bearer {op_token}"}
    )
    assert response.status_code == 403

def test_login_nonexistent_user():
    response = client.post("/auth/login", json={"username": "does_not_exist", "password": "mypassword"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"

def test_login_inactive_user():
    username = f"inactive_{uuid.uuid4()}"
    password = "mypassword"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (username, password_hash, role_id, is_active)
        VALUES (?, ?, ?, 0)
    """, (username, get_password_hash(password), 2))
    conn.commit()
    conn.close()
    
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"

def test_create_user_already_exists(admin_token):
    username = f"duplicate_{uuid.uuid4()}"
    
    # Create the user once
    response1 = client.post(
        "/auth/users", 
        json={"username": username, "role_id": 2},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response1.status_code == 201
    
    # Try creating the exact same user again
    response2 = client.post(
        "/auth/users", 
        json={"username": username, "role_id": 2},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response2.status_code == 400
    assert response2.json()["detail"] == "Username already exists or invalid role"

def test_delete_user_success(admin_token):
    username = f"todelete_{uuid.uuid4()}"
    client.post("/auth/users", json={"username": username, "role_id": 2}, headers={"Authorization": f"Bearer {admin_token}"})
    
    response = client.delete(f"/auth/users/{username}", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    assert response.json()["message"] == "User deleted successfully"
    
    # Verify user is actually deleted
    login_response = client.post("/auth/login", json={"username": username, "password": username})
    assert login_response.status_code == 401

def test_delete_user_not_found(admin_token):
    response = client.delete("/auth/users/nonexistent_user", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 404

def test_delete_user_forbidden():
    op_token = create_access_token(user_id=1, role="operator")
    response = client.delete("/auth/users/someuser", headers={"Authorization": f"Bearer {op_token}"})
    assert response.status_code == 403

def test_admin_reset_password(admin_token):
    username = f"resetme_{uuid.uuid4()}"
    client.post("/auth/users", json={"username": username, "role_id": 2}, headers={"Authorization": f"Bearer {admin_token}"})
    
    response = client.put(f"/auth/users/{username}/password", json={"new_password": "newadminpassword"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    
    login_response = client.post("/auth/login", json={"username": username, "password": "newadminpassword"})
    assert login_response.status_code == 200
    assert "token" in login_response.json()

def test_admin_reset_password_not_found(admin_token):
    response = client.put("/auth/users/nonexistent/password", json={"new_password": "pwd"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 404

def test_admin_reset_password_forbidden():
    op_token = create_access_token(user_id=1, role="operator")
    response = client.put("/auth/users/someuser/password", json={"new_password": "pwd"}, headers={"Authorization": f"Bearer {op_token}"})
    assert response.status_code == 403

def test_update_own_password():
    username = f"selfupdate_{uuid.uuid4()}"
    password = "oldpassword"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (username, password_hash, role_id) VALUES (?, ?, ?)", (username, get_password_hash(password), 2))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    user_token = create_access_token(user_id, "operator")
    
    response = client.put("/auth/password", json={"old_password": password, "new_password": "brandnewpassword"}, headers={"Authorization": f"Bearer {user_token}"})
    assert response.status_code == 200
    
    login_response = client.post("/auth/login", json={"username": username, "password": "brandnewpassword"})
    assert login_response.status_code == 200
    assert "token" in login_response.json()

def test_update_own_password_wrong_old():
    username = f"selfupdate2_{uuid.uuid4()}"
    password = "oldpassword"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (username, password_hash, role_id) VALUES (?, ?, ?)", (username, get_password_hash(password), 2))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    user_token = create_access_token(user_id, "operator")
    
    response = client.put("/auth/password", json={"old_password": "wrongpassword", "new_password": "brandnewpassword"}, headers={"Authorization": f"Bearer {user_token}"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid current password"

def test_update_own_password_unauthorized():
    response = client.put("/auth/password", json={"old_password": "pwd", "new_password": "newpwd"})
    assert response.status_code == 401
