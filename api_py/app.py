
from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import bcrypt
import jwt
import os
from datetime import datetime, timedelta
import functools
import tempfile

app = Flask(__name__)
CORS(app)

# Use /tmp for Railway, current dir otherwise
if os.path.exists('/tmp'):
    DB_PATH = '/tmp/stories.db'
else:
    DB_PATH = './stories.db'

JWT_SECRET = os.environ.get('JWT_SECRET', 'changeme')
UPLOAD_PASSWORD = os.environ.get('UPLOAD_PASSWORD', '2040')
PORT = int(os.environ.get('PORT', 5000))
DEBUG = os.environ.get('FLASK_ENV') == 'development'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS stories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        text TEXT,
        image TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('SELECT * FROM users WHERE username = ?', ('admin',))
    if not c.fetchone():
        hash_pw = bcrypt.hashpw('admin'.encode(), bcrypt.gensalt())
        c.execute('INSERT INTO users (username, password) VALUES (?, ?)', ('admin', hash_pw))
    conn.commit()
    conn.close()

def authenticate_token(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get('Authorization', None)
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'No token'}), 401
        token = auth_header.split(' ')[1]
        try:
            user = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            request.user = user
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 403
        return f(*args, **kwargs)
    return wrapper

# Health check
@app.route('/ping', methods=['GET'])
def ping():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT 1')
        conn.close()
        return jsonify({'message': 'pong', 'db': 'ok'})
    except Exception as e:
        return jsonify({'message': 'pong', 'db': 'error', 'error': str(e)}), 200

# Auth route
@app.route('/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        conn.close()
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401
        if not bcrypt.checkpw(password.encode(), user['password']):
            return jsonify({'error': 'Invalid credentials'}), 401
        token = jwt.encode({'username': user['username'], 'id': user['id'], 'exp': datetime.utcnow() + timedelta(hours=2)}, JWT_SECRET, algorithm='HS256')
        return jsonify({'token': token})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Verify upload password
@app.route('/auth/verify-upload-password', methods=['POST'])
def verify_upload_password():
    data = request.get_json()
    password = data.get('password')
    if not password:
        return jsonify({'error': 'Password required'}), 400
    if password == UPLOAD_PASSWORD:
        return jsonify({'success': True})
    return jsonify({'error': 'Invalid password'}), 401

# Get stories
@app.route('/stories', methods=['GET'])
def get_stories():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM stories ORDER BY created_at DESC')
        rows = c.fetchall()
        stories = [dict(row) for row in rows]
        conn.close()
        return jsonify(stories)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Create story
@app.route('/stories', methods=['POST'])
@authenticate_token
def create_story():
    try:
        data = request.get_json()
        name = data.get('name', 'Anonymous')
        text = data.get('text')
        image = data.get('image', '')
        if not text:
            return jsonify({'error': 'Text required'}), 400
        conn = get_db()
        c = conn.cursor()
        c.execute('INSERT INTO stories (name, text, image) VALUES (?, ?, ?)', (name, text, image))
        conn.commit()
        result_id = c.lastrowid
        conn.close()
        return jsonify({'id': result_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Update story
@app.route('/stories/<int:id>', methods=['PUT'])
@authenticate_token
def update_story(id):
    try:
        data = request.get_json()
        name = data.get('name')
        text = data.get('text')
        image = data.get('image')
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE stories SET name = ?, text = ?, image = ? WHERE id = ?', (name, text, image, id))
        conn.commit()
        rowcount = c.rowcount
        conn.close()
        return jsonify({'updated': rowcount})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Delete story
@app.route('/stories/<int:id>', methods=['DELETE'])
@authenticate_token
def delete_story(id):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('DELETE FROM stories WHERE id = ?', (id,))
        conn.commit()
        rowcount = c.rowcount
        conn.close()
        return jsonify({'deleted': rowcount})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    try:
        init_db()
    except Exception as e:
        print(f'Database initialization error: {e}')
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG)
