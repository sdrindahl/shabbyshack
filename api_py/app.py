
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import sqlite3
import bcrypt
import jwt
import os
from datetime import datetime, timedelta
import functools
import tempfile
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Use /tmp for Railway, current dir otherwise
if os.path.exists('/tmp'):
    DB_PATH = '/tmp/stories.db'
else:
    DB_PATH = './stories.db'

logger.info(f'Database path: {DB_PATH}')

JWT_SECRET = os.environ.get('JWT_SECRET', 'changeme')
UPLOAD_PASSWORD = os.environ.get('UPLOAD_PASSWORD', '2040')
PORT = int(os.environ.get('PORT', 5000))
DEBUG = os.environ.get('FLASK_ENV') == 'development'

logger.info(f'Starting app with PORT={PORT}, DEBUG={DEBUG}')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    try:
        logger.info(f'Initializing database at {DB_PATH}')
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
            logger.info('Creating default admin user')
            hash_pw = bcrypt.hashpw('admin'.encode(), bcrypt.gensalt())
            c.execute('INSERT INTO users (username, password) VALUES (?, ?)', ('admin', hash_pw))
        conn.commit()
        conn.close()
        logger.info('Database initialized successfully')
    except Exception as e:
        logger.error(f'Database initialization failed: {e}', exc_info=True)
        raise

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
    try:
        data = request.get_json()
        password = data.get('password')
        logger.info(f'Password verification attempt: received="{password}", expected="{UPLOAD_PASSWORD}"')
        if not password:
            logger.warning('Password verification failed: no password provided')
            return jsonify({'error': 'Password required'}), 400
        if password == UPLOAD_PASSWORD:
            logger.info('Password verification successful')
            return jsonify({'success': True})
        logger.warning(f'Password verification failed: password mismatch')
        return jsonify({'error': 'Invalid password'}), 401
    except Exception as e:
        logger.error(f'Password verification error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500

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

# Serve HTML files from parent directory
@app.route('/')
def index():
    return send_from_directory('../', 'index.html')

@app.route('/<path:filename>')
def serve_html(filename):
    # Check if it's an HTML file in parent directory
    if filename.endswith('.html') or filename.endswith('.css') or filename.endswith('.js'):
        try:
            return send_from_directory('../', filename)
        except:
            pass
    # Check if it's an image or other asset
    try:
        return send_from_directory('../', filename)
    except:
        return jsonify({'error': 'Not found'}), 404

# Global error handlers
@app.errorhandler(404)
def not_found(error):
    logger.warning(f'404 error: {request.path} - {error}')
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f'500 Internal Server Error: {error}', exc_info=True)
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(Exception)
def handle_exception(error):
    logger.error(f'Unhandled exception: {error}', exc_info=True)
    return jsonify({'error': 'Internal server error', 'type': type(error).__name__}), 500

# Initialize database at module load time for both dev and production
try:
    logger.info('Initializing database at module load...')
    init_db()
    logger.info('Database initialization complete')
except Exception as e:
    logger.error(f'Failed to initialize database at startup: {e}', exc_info=True)
    logger.warning('Database initialization failed but app will continue')

if __name__ == '__main__':
    logger.info(f'Flask app starting on 0.0.0.0:{PORT} (debug={DEBUG})')
    try:
        app.run(host='0.0.0.0', port=PORT, debug=DEBUG, use_reloader=False)
    except Exception as e:
        logger.error(f'Flask app crashed: {e}', exc_info=True)
        sys.exit(1)
