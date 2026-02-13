const express = require('express');
const cors = require('cors');
const sqlite3 = require('sqlite3').verbose();
const bcrypt = require('bcrypt');
const jwt = require('jsonwebtoken');
require('dotenv').config();

const app = express();
app.use(cors());
app.use(express.json({ limit: '10mb' }));

// Health check
app.get('/ping', (req, res) => {
  res.json({ message: 'pong' });
});

// SQLite setup
const db = new sqlite3.Database('./stories.db');
db.serialize(() => {
  db.run(`CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT
  )`);
  db.run(`CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    text TEXT,
    image TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )`);
  // Create default admin if not exists
  db.get('SELECT * FROM users WHERE username = ?', ['admin'], (err, row) => {
    if (!row) {
      bcrypt.hash('admin', 10, (err, hash) => {
        db.run('INSERT INTO users (username, password) VALUES (?, ?)', ['admin', hash]);
      });
    }
  });
});

// Auth middleware
const JWT_SECRET = process.env.JWT_SECRET || 'changeme';
const UPLOAD_PASSWORD = process.env.UPLOAD_PASSWORD || '2040';

function authenticateToken(req, res, next) {
  const authHeader = req.headers['authorization'];
  const token = authHeader && authHeader.split(' ')[1];
  if (!token) return res.status(401).json({ error: 'No token' });
  jwt.verify(token, JWT_SECRET, (err, user) => {
    if (err) return res.status(403).json({ error: 'Invalid token' });
    req.user = user;
    next();
  });
}

// Verify upload password
app.post('/auth/verify-upload-password', (req, res) => {
  const { password } = req.body;
  if (!password) return res.status(400).json({ error: 'Password required' });
  if (password === UPLOAD_PASSWORD) {
    return res.json({ success: true });
  }
  return res.status(401).json({ error: 'Invalid password' });
});

// Auth routes
app.post('/auth/login', (req, res) => {
  const { username, password } = req.body;
  db.get('SELECT * FROM users WHERE username = ?', [username], (err, user) => {
    if (!user) return res.status(401).json({ error: 'Invalid credentials' });
    bcrypt.compare(password, user.password, (err, result) => {
      if (!result) return res.status(401).json({ error: 'Invalid credentials' });
      const token = jwt.sign({ username: user.username, id: user.id }, JWT_SECRET, { expiresIn: '2h' });
      res.json({ token });
    });
  });
});

// Story routes
app.get('/stories', (req, res) => {
  db.all('SELECT * FROM stories ORDER BY created_at DESC', [], (err, rows) => {
    if (err) {
      console.error('Error fetching stories:', err);
      return res.status(500).json({ error: err.message });
    }
    res.json(rows);
  });
});

app.post('/stories', authenticateToken, (req, res) => {
  const { name, text, image } = req.body;
  if (!text) return res.status(400).json({ error: 'Text required' });
  db.run('INSERT INTO stories (name, text, image) VALUES (?, ?, ?)', [name || 'Anonymous', text, image || ''], function(err) {
    if (err) return res.status(500).json({ error: err.message });
    res.json({ id: this.lastID });
  });
});

app.put('/stories/:id', authenticateToken, (req, res) => {
  const { name, text, image } = req.body;
  db.run('UPDATE stories SET name = ?, text = ?, image = ? WHERE id = ?', [name, text, image, req.params.id], function(err) {
    if (err) return res.status(500).json({ error: err.message });
    res.json({ updated: this.changes });
  });
});

app.delete('/stories/:id', authenticateToken, (req, res) => {
  db.run('DELETE FROM stories WHERE id = ?', [req.params.id], function(err) {
    if (err) return res.status(500).json({ error: err.message });
    res.json({ deleted: this.changes });
  });
});

// Delete multiple stories with password verification
app.post('/stories/delete-with-password', (req, res) => {
  const { password, ids } = req.body;
  
  if (!password) {
    return res.status(400).json({ error: 'Password required' });
  }
  
  if (!Array.isArray(ids) || ids.length === 0) {
    return res.status(400).json({ error: 'No stories selected' });
  }
  
  // Verify password
  if (password !== UPLOAD_PASSWORD) {
    return res.status(401).json({ error: 'Invalid password' });
  }
  
  // Delete all stories with provided IDs
  const placeholders = ids.map(() => '?').join(',');
  const query = `DELETE FROM stories WHERE id IN (${placeholders})`;
  
  db.run(query, ids, function(err) {
    if (err) {
      console.error('Error deleting stories:', err);
      return res.status(500).json({ error: err.message });
    }
    res.json({ success: true, deleted: this.changes });
  });
});

const PORT = process.env.PORT;
console.log('process.env.PORT:', process.env.PORT);
if (!PORT) {
  console.error('PORT is not set!');
  process.exit(1);
}
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});