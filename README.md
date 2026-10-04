# AgentGuard

Monorepo with a FastAPI backend and a React (Vite + TypeScript) frontend.

## Structure

```
backend/   FastAPI app
frontend/  React + Vite app
```

## Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # already created
uvicorn app.main:app --reload --port 8000
```

API available at http://localhost:8000 (docs at `/docs`).

## Frontend

```bash
cd frontend
npm install
cp .env.example .env   # already created
npm run dev
```

App available at http://localhost:5173.
