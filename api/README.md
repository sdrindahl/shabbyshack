# Shabbyshack API Backend

This is a Node.js (Express) backend for story sharing with authentication and SQLite storage.

## Features
- REST API for stories: list, add, edit, delete
- SQLite database (file-based, easy Railway deployment)
- Simple username/password authentication (JWT-based)
- Only authenticated users can add/edit/delete

## Quickstart

1. Install dependencies:
   ```sh
   npm install
   ```
2. Start the server (dev):
   ```sh
   npm run dev
   ```
3. Start the server (prod):
   ```sh
   npm start
   ```

## Railway Deployment
- Push this folder to a GitHub repo and connect it to Railway.
- Set the environment variable `JWT_SECRET` in Railway for security.
- Railway will auto-detect and deploy the Node.js app.

## API Endpoints
- `POST   /auth/login` — Login, returns JWT
- `GET    /stories` — List all stories
- `POST   /stories` — Add a new story (auth required)
- `PUT    /stories/:id` — Edit a story (auth required)
- `DELETE /stories/:id` — Delete a story (auth required)

## Frontend Integration
- Use `fetch` or AJAX to call these endpoints from your static site.
- Send the JWT as an `Authorization: Bearer <token>` header for protected routes.

---

Replace the default admin credentials after first deploy!
