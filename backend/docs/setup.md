# Setup Guide

## Requirements

- Python 3.12+
- PostgreSQL (running)
- pip

## Installation

### 1. Clone the repository

```bash
git clone <repo-url>
cd EduBot
```

### 2. Create virtual environment

```bash
python -m venv .venv
```

Activate:

- Windows: `.venv\Scripts\activate`
- Linux/Mac: `source .venv/bin/activate`

### 3. Install dependencies

```bash
pip install -r backend/requirements.txt
```

### 4. Configure environment

Edit `backend/.env`:

```env
DATABASE_URL=postgresql://user:password@host:port/edubot
JWT_SECRET_KEY=your-secure-random-secret-key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

### 5. Create the database

```bash
createdb edubot
```

### 6. Run migrations

```bash
cd backend
alembic upgrade head
```

### 7. Start the server

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### 8. Open Swagger UI

http://localhost:8000/docs

## Testing the API

Recommended flow:

1. Create a school via `POST /schools` (requires auth — first create a school_admin via registration)
2. Register a user via `POST /auth/register`
3. Login via `POST /auth/login` to get a JWT token
4. Use the "Authorize" button in Swagger UI to set the token
5. Test all protected endpoints

## Database Migrations

```bash
# Auto-generate a migration after model changes
alembic revision --autogenerate -m "description"

# Apply pending migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1

# View history
alembic history
```
