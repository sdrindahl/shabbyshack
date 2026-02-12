
from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import bcrypt
import jwt
import os
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

DB_PATH = './stories.db'
JWT_SECRET = os.environ.get('JWT_SECRET', 'changeme')
UPLOAD_PASSWORD = os.environ.get('UPLOAD_PASSWORD', '2040')
PORT = int(os.environ.get('PORT', 5000))

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
    wrapper.__name__ = f.__name__
    return wrapper

# Health check
@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({'message': 'pong'})

# Auth route
@app.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = c.fetchone()
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    if not bcrypt.checkpw(password.encode(), user['password']):
        return jsonify({'error': 'Invalid credentials'}), 401
    token = jwt.encode({'username': user['username'], 'id': user['id'], 'exp': datetime.utcnow() + timedelta(hours=2)}, JWT_SECRET, algorithm='HS256')
    return jsonify({'token': token})

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
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM stories ORDER BY created_at DESC')
    rows = c.fetchall()
    stories = [dict(row) for row in rows]
    return jsonify(stories)

# Create story
@app.route('/stories', methods=['POST'])
@authenticate_token
def create_story():
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
    return jsonify({'id': c.lastrowid})

# Update story
@app.route('/stories/<int:id>', methods=['PUT'])
@authenticate_token
def update_story(id):
    data = request.get_json()
    name = data.get('name')
    text = data.get('text')
    image = data.get('image')
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE stories SET name = ?, text = ?, image = ? WHERE id = ?', (name, text, image, id))
    conn.commit()
    return jsonify({'updated': c.rowcount})

# Delete story
@app.route('/stories/<int:id>', methods=['DELETE'])
@authenticate_token
def delete_story(id):
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM stories WHERE id = ?', (id,))
    conn.commit()
    return jsonify({'deleted': c.rowcount})

if __name__ == '__main__':
    init_db()
    app.run(port=PORT, debug=True)
