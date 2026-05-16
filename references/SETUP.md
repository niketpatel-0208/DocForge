# Setup Guide

## Requirements

- Python 3.12+
- Node.js 18+ and npm
- GitLab Personal Access Token (`read_api`, `read_repository` scopes)
- LiteLLM API key from your team

## Backend

```bash
cd backend
python -m venv venv

# Windows
.\venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

Edit `backend/.env`:

```env
LITELLM_API_KEY=sk-YOUR_KEY_HERE
LLM_MODEL=anthropic/claude-sonnet-4-6
ALLOWED_ORIGINS=http://localhost:3000
CACHE_TTL_SECONDS=600
```

Start:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Frontend

```bash
cd frontend
npm install
npm start
# Opens at http://localhost:3000
```

## GitLab PAT Creation

1. Log in to your GitLab instance
2. Click avatar → **Edit profile**
3. Left sidebar → **Access Tokens**
4. Fill in token name, expiration date
5. Select scopes: `read_api` + `read_repository`
6. Click **Create personal access token** — copy immediately

## Troubleshooting

| Error | Fix |
|---|---|
| `LITELLM_API_KEY not configured` | Set `LITELLM_API_KEY` in `backend/.env` |
| `GitLab token invalid` | Verify `read_api` + `read_repository` scopes |
| `Could not resolve repository` | Use full HTTPS URL, not SSH |
| `CORS error` | Check `ALLOWED_ORIGINS` matches your frontend URL |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` with venv active |