# Shabbyshack API Backend

## Usage

1. Install dependencies:
   npm install

2. Start the server (dev):
   npm run dev

3. Start the server (prod):
   npm start

## Default Admin Login
- Username: admin
- Password: admin

Change the admin password after first deploy!

## Railway Deployment
- Push this folder to a GitHub repo and connect it to Railway.
- Set the environment variable JWT_SECRET in Railway for security.

## API Endpoints
- POST   /auth/login — Login, returns JWT
- GET    /stories — List all stories
- POST   /stories — Add a new story (auth required)
- PUT    /stories/:id — Edit a story (auth required)
- DELETE /stories/:id — Delete a story (auth required)

## Frontend Integration Example
```js
// Login
fetch('https://<your-railway-url>/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'admin', password: 'admin' })
})
  .then(res => res.json())
  .then(data => localStorage.setItem('token', data.token));

// Add a story
fetch('https://<your-railway-url>/stories', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ' + localStorage.getItem('token')
  },
  body: JSON.stringify({ name: 'Scott', text: 'My story', image: '' })
});
```
