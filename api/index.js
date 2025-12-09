require('dotenv').config();
const express = require('express');
const cors = require('cors');
const sqlite3 = require('sqlite3').verbose();
const fs = require('fs');
const jwt = require('jsonwebtoken');
const bcrypt = require('bcrypt');

const app = express();
const PORT = process.env.PORT || 8080;
const JWT_SECRET = process.env.JWT_SECRET || 'changeme';

app.use(cors());
app.use(express.json());

// --- SQLite setup ---
// Ensure /data directory exists (for Railway persistent storage)
const dataDir = '/data';
if (!fs.existsSync(dataDir)) {
  fs.mkdirSync(dataDir);
}
const db = new sqlite3.Database('/data/stories.db');

// Log all requests for debugging
app.use((req, res, next) => {
  console.log(`[${new Date().toISOString()}] ${req.method} ${req.url}`);
  next();
});
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

// --- Auth Middleware ---
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

// --- Auth Routes ---
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

// --- Story Routes ---
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

app.listen(PORT, () => {
  console.log(`API server running on port ${PORT}`);
});
