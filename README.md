# DrKaset Agricultural AI Assistant

DrKaset is a full-stack agricultural assistant for Thai farmers. It combines a React chat interface, a FastAPI backend, MySQL user/chat history storage, FAISS vector search, and Ollama language models to answer agriculture questions from prepared reference documents.

## Screenshots

<p align="center">
  <img src="docs/screenshots/app.png" alt="DrKaset app screenshot" width="800">
  <br>
  <img src="docs/screenshots/overview.png" alt="Project overview screenshot" width="800">
</p>

## Features

- User registration, login, JWT refresh, and protected chat history.
- RAG question answering from local FAISS index data.
- Streaming chat responses from the backend.
- Chat session and message history stored in MySQL.
- Health check endpoint for backend dependencies.
- Weather and market price API endpoints.
- Data preparation pipeline for cleaning, chunking, embedding, and indexing agriculture documents.

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | React 18, Vite, Axios, React Router, React Markdown |
| Backend | FastAPI, SQLAlchemy, Pydantic, python-jose, bcrypt |
| AI/RAG | Ollama, LangChain, sentence-transformers, FAISS |
| Database | MySQL |

## Project Structure

```text
CSI_AI_DrKaset/
  backend/
    main.py
    config.py
    database.py
    api/
    auth/
    db/
    rag/
    schemas/
    data/faiss_index/
  frontend/
    src/
  data_preparation/
  db/
    init.sql
    migrations/
```

## Environment Variables

Create `backend/.env` from `backend/.env.example`.

## Database Setup

```bash
mysql -u root -p < db/init.sql
```

The schema is documented in `DATABASE_SCHEMA.md`.

## Run Locally

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

Default local URLs:

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

## API Overview

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/auth/register` | Register user and return token |
| `POST` | `/auth/login` | Login and return token |
| `POST` | `/auth/refresh` | Refresh token |
| `POST` | `/chat` | Send chat message and stream answer |
| `GET` | `/chat/sessions` | List chat sessions |
| `GET` | `/chat/sessions/{session_id}/messages` | List messages in a session |
| `DELETE` | `/chat/sessions/{session_id}` | Delete a chat session |
| `GET` | `/health` | Backend health check |
| `GET` | `/weather` | Weather data endpoint |
| `GET` | `/market-prices` | Market price endpoint |

## GitHub Notes

Before publishing, do not commit `backend/venv/`, `.venv/`, `__pycache__/`, `frontend/node_modules/`, `frontend/dist/`, `.env`, or large/generated FAISS indexes unless intentionally included.
