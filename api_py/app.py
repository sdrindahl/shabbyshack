
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

# Get the parent directory (project root) from the api_py directory
APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(APP_DIR)
logger.info(f'APP_DIR: {APP_DIR}')
logger.info(f'PROJECT_ROOT: {PROJECT_ROOT}')

app = Flask(__name__)
CORS(app)

# Database initialization flag
_db_initialized = False

def ensure_db_initialized():
    """Lazy-initialize database on first use"""
    global _db_initialized
    if _db_initialized:
        return
    try:
        init_db()
        _db_initialized = True
    except Exception as e:
        logger.error(f'Failed to initialize database: {e}', exc_info=True)
        # Don't crash - try again on next request

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
logger.info('Delete endpoint is active and ready')

# Force Railway rebuild - ensure delete-with-password endpoint is active
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    try:
        logger.info(f'Initializing database at {DB_PATH}')
        
        conn = get_db()
        c = conn.cursor()
        
        # STEP 1: Check if stories table exists with OLD schema
        c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='stories'")
        existing_sql = c.fetchone()
        
        if existing_sql:
            create_sql_str = str(existing_sql[0]).upper()
            logger.warning(f'Existing stories table found. SQL: {existing_sql[0]}')
            
            # If it has DATETIME or TEXT for created_at, DROP and recreate
            if 'DATETIME' in create_sql_str or ('CREATED_AT' in create_sql_str and 'TEXT' in create_sql_str):
                logger.warning('OLD SCHEMA DETECTED! Dropping stories table...')
                c.execute('DROP TABLE IF EXISTS stories')
                conn.commit()
                logger.warning('Stories table dropped. Will recreate with INTEGER schema.')
                existing_sql = None
        
        # STEP 2: Create users table
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )''')
        
        # STEP 3: Create stories table with INTEGER timestamps
        if not existing_sql:
            logger.info('Creating new stories table with INTEGER timestamps')
            c.execute('''CREATE TABLE IF NOT EXISTS stories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                text TEXT,
                image TEXT,
                created_at INTEGER NOT NULL DEFAULT 0
            )''')
            
            # Verify the schema
            c.execute("PRAGMA table_info(stories)")
            columns = c.fetchall()
            logger.info('=== NEW STORIES TABLE SCHEMA ===')
            for col in columns:
                logger.info(f'  Column {col[1]}: Type={col[2]}, NotNull={col[3]}, Default={col[4]}')
        
        # STEP 4: Create admin user
        c.execute('SELECT * FROM users WHERE username = ?', ('admin',))
        if not c.fetchone():
            logger.info('Creating default admin user')
            hash_pw = bcrypt.hashpw('admin'.encode(), bcrypt.gensalt())
            c.execute('INSERT INTO users (username, password) VALUES (?, ?)', ('admin', hash_pw))
        
        conn.commit()
        conn.close()
        logger.info('=== DATABASE INITIALIZATION COMPLETE ===')
    except Exception as e:
        logger.error(f'Database initialization failed: {e}', exc_info=True)
        raise

def authenticate_token(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get('Authorization', None)
        if not auth_header or not auth_header.startswith('Bearer '):
            logger.warning('Missing or invalid Authorization header')
            return jsonify({'error': 'No token'}), 401
        token = auth_header.split(' ')[1]
        try:
            user = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            logger.info(f'Token authenticated for user: {user.get("username")}')
            request.user = user
        except jwt.InvalidTokenError as e:
            logger.warning(f'Invalid token: {e}')
            return jsonify({'error': 'Invalid token'}), 403
        except Exception as e:
            logger.error(f'Token authentication error: {e}', exc_info=True)
            return jsonify({'error': 'Authentication error'}), 500
        return f(*args, **kwargs)
    return wrapper

# Health check
@app.route('/ping', methods=['GET'])
def ping():
    try:
        ensure_db_initialized()
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT 1')
        conn.close()
        return jsonify({'message': 'pong', 'db': 'ok'})
    except Exception as e:
        logger.warning(f'Health check DB error: {e}')
        return jsonify({'message': 'pong', 'db': 'error', 'error': str(e)}), 200

@app.route('/test-new-route', methods=['GET'])
def test_new_route():
    return jsonify({'message': 'New route working - code deployed!'}), 200

# Auth route
@app.route('/auth/login', methods=['POST'])
def login():
    try:
        ensure_db_initialized()
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        logger.info(f'Login attempt for user: {username}')
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        conn.close()
        if not user:
            logger.warning(f'Login failed: user {username} not found')
            return jsonify({'error': 'Invalid credentials'}), 401
        if not bcrypt.checkpw(password.encode(), user['password']):
            logger.warning(f'Login failed: invalid password for user {username}')
            return jsonify({'error': 'Invalid credentials'}), 401
        token = jwt.encode({'username': user['username'], 'id': user['id'], 'exp': datetime.utcnow() + timedelta(hours=2)}, JWT_SECRET, algorithm='HS256')
        logger.info(f'Login successful for user: {username}')
        return jsonify({'token': token})
    except Exception as e:
        logger.error(f'Login error: {e}', exc_info=True)
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
        ensure_db_initialized()
        conn = get_db()
        c = conn.cursor()
        
        # Debug: log the actual schema
        c.execute("PRAGMA table_info(stories)")
        schema = c.fetchall()
        logger.info(f'Stories table schema:')
        for col in schema:
            logger.info(f'  Column: {col[1]}, Type: {col[2]}')
        
        c.execute('SELECT * FROM stories ORDER BY created_at DESC')
        rows = c.fetchall()
        stories = [dict(row) for row in rows]
        
        logger.info(f'Retrieved {len(stories)} stories from database')
        if stories:
            first_ts = stories[0].get("created_at")
            logger.info(f'First story created_at: {repr(first_ts)} (type: {type(first_ts).__name__})')
            
            # Log a few more details
            logger.info(f'First story full: id={stories[0].get("id")}, name={stories[0].get("name")}, created_at_value={first_ts}')
        
        return jsonify(stories)
    except Exception as e:
        logger.error(f'Get stories error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500

# Create story
@app.route('/stories', methods=['POST'])
@authenticate_token
def create_story():
    try:
        ensure_db_initialized()
        logger.info('Create story endpoint called')
        
        # Handle both JSON and FormData
        if request.is_json:
            # JSON payload (legacy)
            data = request.get_json()
            name = data.get('name', 'Anonymous')
            text = data.get('text') or 'Uploaded photo'  # Ensure default if empty or None
            image = data.get('image', '')
            timestamp = data.get('timestamp', None)  # Client-provided timestamp
            logger.info(f'JSON payload: name={name}, timestamp={timestamp}, type={type(timestamp).__name__}')
            if not image:
                logger.warning('No image data in JSON payload')
                return jsonify({'error': 'Image required'}), 400
        else:
            # FormData payload (files)
            logger.info(f'FormData keys: {list(request.form.keys())}')
            logger.info(f'Files keys: {list(request.files.keys())}')
            
            name = request.form.get('name', 'Anonymous')
            text = request.form.get('text') or 'Uploaded photo'  # Ensure default if empty or None
            timestamp = request.form.get('timestamp', None)  # Client-provided timestamp
            
            logger.info(f'Parsed FormData: name={name}, timestamp={timestamp}, type={type(timestamp).__name__}')
            
            if 'image' not in request.files:
                logger.warning('No image file in FormData')
                return jsonify({'error': 'Image file required'}), 400
            
            file = request.files['image']
            if file.filename == '':
                logger.warning('Empty filename in upload')
                return jsonify({'error': 'No file selected'}), 400
            
            # Read the file and encode to base64
            import base64
            file_data = file.read()
            image = f'data:{file.content_type};base64,' + base64.b64encode(file_data).decode('utf-8')
            logger.info(f'File received: {file.filename}, size: {len(file_data)} bytes')
        
        if not image:
            logger.warning('No image data provided')
            return jsonify({'error': 'Image required'}), 400
        
        # Use client timestamp if provided, otherwise use server time (in milliseconds)
        if not timestamp:
            import time
            timestamp = int(time.time() * 1000)  # Convert to milliseconds
            logger.info(f'Using server timestamp: {timestamp}')
        else:
            # Ensure timestamp is an integer (milliseconds)
            try:
                timestamp = int(timestamp)
                logger.info(f'Using client timestamp: {timestamp}')
            except (ValueError, TypeError):
                import time
                timestamp = int(time.time() * 1000)  # Fallback to server time
                logger.warning(f'Could not convert timestamp, using server time: {timestamp}')
        
        conn = get_db()
        c = conn.cursor()
        c.execute('INSERT INTO stories (name, text, image, created_at) VALUES (?, ?, ?, ?)', (name, text, image, timestamp))
        conn.commit()
        result_id = c.lastrowid
        conn.close()
        logger.info(f'Story created: id={result_id}, stored_timestamp={timestamp}')
        return jsonify({'id': result_id})
    except Exception as e:
        logger.error(f'Failed to create story: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500

# Update story
@app.route('/stories/<int:id>', methods=['PUT'])
@authenticate_token
def update_story(id):
    try:
        ensure_db_initialized()
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

# Delete stories with password verification
# This endpoint allows bulk deletion with password authentication
# Trigger Railway rebuild to activate endpoint
@app.route('/stories/delete-with-password', methods=['POST'])
def delete_stories_with_password():
    try:
        ensure_db_initialized()
        data = request.get_json()
        password = data.get('password')
        ids = data.get('ids', [])
        
        logger.info(f'Delete with password attempt: {len(ids)} stories, password provided: {bool(password)}')
        
        if not password:
            logger.warning('Delete with password failed: no password provided')
            return jsonify({'error': 'Password required'}), 400
        
        if not isinstance(ids, list) or len(ids) == 0:
            logger.warning('Delete with password failed: no story IDs provided')
            return jsonify({'error': 'No stories selected'}), 400
        
        # Verify password
        if password != UPLOAD_PASSWORD:
            logger.warning(f'Delete with password failed: password mismatch')
            return jsonify({'error': 'Invalid password'}), 401
        
        logger.info(f'Password verified, deleting {len(ids)} stories: {ids}')
        
        # Delete all stories with provided IDs
        conn = get_db()
        c = conn.cursor()
        
        # Delete each story
        deleted_count = 0
        for story_id in ids:
            c.execute('DELETE FROM stories WHERE id = ?', (story_id,))
            deleted_count += c.rowcount
        
        conn.commit()
        conn.close()
        
        logger.info(f'Successfully deleted {deleted_count} stories')
        return jsonify({'success': True, 'deleted': deleted_count})
    except Exception as e:
        logger.error(f'Failed to delete stories with password: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500

# Delete story
@app.route('/stories/<int:id>', methods=['DELETE'])
@authenticate_token
def delete_story(id):
    try:
        ensure_db_initialized()
        conn = get_db()
        c = conn.cursor()
        c.execute('DELETE FROM stories WHERE id = ?', (id,))
        conn.commit()
        rowcount = c.rowcount
        conn.close()
        return jsonify({'deleted': rowcount})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Serve HTML files from project root
@app.route('/')
def index():
    try:
        return send_from_directory(PROJECT_ROOT, 'index.html')
    except Exception as e:
        logger.error(f'Failed to serve index.html: {e}')
        return jsonify({'error': 'Not found'}), 404

@app.route('/<path:filename>')
def serve_file(filename):
    try:
        file_path = os.path.join(PROJECT_ROOT, filename)
        # Prevent directory traversal
        if not os.path.abspath(file_path).startswith(os.path.abspath(PROJECT_ROOT)):
            logger.warning(f'Attempted directory traversal: {filename}')
            return jsonify({'error': 'Not found'}), 404
        logger.debug(f'Serving file: {file_path}')
        return send_from_directory(PROJECT_ROOT, filename)
    except Exception as e:
        logger.debug(f'File not found: {filename} - {e}')
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

# Flask app initialization complete - database will be initialized on first use
logger.info(f'Flask app initialized, ready to start on 0.0.0.0:{PORT}')

if __name__ == '__main__':
    logger.info(f'Flask app starting on 0.0.0.0:{PORT} (debug={DEBUG})')
    try:
        app.run(host='0.0.0.0', port=PORT, debug=DEBUG, use_reloader=False)
    except Exception as e:
        logger.error(f'Flask app crashed: {e}', exc_info=True)
        sys.exit(1)
