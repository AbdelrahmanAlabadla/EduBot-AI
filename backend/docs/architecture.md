# Architecture

## Overview

EduBot AI backend follows a **layered architecture** with clear separation of concerns: API routes, business logic, data access, and database are isolated into distinct layers.

## Folder Structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI app initialization, router registration
│   ├── database/
│   │   ├── connection.py       # SQLAlchemy engine, SessionLocal, get_db dependency
│   │   └── base.py             # SQLAlchemy Base (declarative base for all models)
│   ├── models/
│   │   ├── school.py           # School ORM model
│   │   ├── user.py             # User ORM model
│   │   └── __init__.py         # Re-exports models for Alembic
│   ├── schemas/
│   │   ├── school.py           # Pydantic schemas for school requests/responses
│   │   └── user.py             # Pydantic schemas for user requests/responses
│   ├── api/
│   │   ├── auth.py             # Authentication endpoints (/auth/*)
│   │   ├── schools.py          # School CRUD endpoints (/schools/*)
│   │   └── users.py            # User CRUD endpoints (/users/*)
│   ├── core/
│   │   ├── config.py           # Pydantic Settings loaded from .env
│   │   └── security.py         # Password hashing and JWT token functions
│   └── dependencies/
│       └── auth.py             # get_current_user FastAPI dependency
├── alembic/                    # Alembic migration scripts
├── docs/                       # Technical documentation
├── .env                        # Environment variables
├── alembic.ini                 # Alembic configuration
└── requirements.txt            # Python dependencies
```

## Responsibilities

| Folder | Responsibility |
|---|---|
| `app/` | Main application package |
| `database/` | Database engine, session management, declarative base |
| `models/` | SQLAlchemy ORM models (database table definitions) |
| `schemas/` | Pydantic models for request validation and response serialization |
| `api/` | FastAPI route handlers |
| `core/` | Configuration loading and security primitives |
| `dependencies/` | Reusable FastAPI dependency injection components |

## Request Flow

```
Client (HTTP Request)
       |
       v
FastAPI Router (app/api/*.py)
       |
       v
Dependency Injection (app/dependencies/auth.py)
  - JWT token validation
  - Database session
       |
       v
Route Handler
  - Request validation via Pydantic schemas
  - Business logic
  - Database queries via SQLAlchemy
       |
       v
SQLAlchemy ORM (app/models/*.py)
       |
       v
PostgreSQL
```

## Design Decisions

- **Stateless API**: JWT tokens carry authentication state; no server-side sessions.
- **Repository pattern not used**: For this scale, direct ORM usage in route handlers is sufficient. Can be refactored to service/repository layers as complexity grows.
- **Multi-tenant by school_id**: All school-scoped queries filter by `school_id` from the authenticated user's token.
