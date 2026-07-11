# Database

## Technology

PostgreSQL with SQLAlchemy ORM (2.0 style) and Alembic for migrations.

## Tables

### schools

The multi-tenant root table. Every user belongs to exactly one school.

| Column     | Type         | Constraints        |
|------------|-------------|--------------------|
| id         | UUID         | PRIMARY KEY         |
| name       | VARCHAR(255) | NOT NULL            |
| slug       | VARCHAR(255) | UNIQUE, NOT NULL    |
| logo_url   | VARCHAR(500) | NULLABLE            |
| website    | VARCHAR(500) | NULLABLE            |
| email      | VARCHAR(255) | NULLABLE            |
| phone      | VARCHAR(50)  | NULLABLE            |
| address    | TEXT         | NULLABLE            |
| language   | VARCHAR(50)  | NULLABLE            |
| status     | VARCHAR(50)  | DEFAULT 'active'    |
| created_at | TIMESTAMP    | DEFAULT now()       |
| updated_at | TIMESTAMP    | DEFAULT now()       |

### users

Users linked to a school. Authentication and role management.

| Column        | Type         | Constraints                    |
|--------------|-------------|--------------------------------|
| id            | UUID         | PRIMARY KEY                    |
| school_id     | UUID         | FOREIGN KEY → schools.id       |
| name          | VARCHAR(255) | NOT NULL                       |
| email         | VARCHAR(255) | UNIQUE, NOT NULL               |
| password_hash | VARCHAR(255) | NOT NULL                       |
| role          | VARCHAR(50)  | NOT NULL                       |
| created_at    | TIMESTAMP    | DEFAULT now()                  |
| updated_at    | TIMESTAMP    | DEFAULT now()                  |

## Relationships

```
schools  1 ──── N  users
```

- A school has many users.
- A user belongs to one school (via `school_id` foreign key).
- Deleting a school cascades to delete its users.

## Future Tables (planned)

| Table | Purpose |
|---|---|
| documents | Uploaded educational documents per school |
| document_chunks | Text chunks from processed documents (for RAG pipeline) |
| conversations | Chat conversations between users and the AI |
| messages | Individual messages within conversations |
| leads | School admission leads/inquiries |

## Migrations

Migrations are managed with Alembic. To create a new migration:

```bash
cd backend
alembic revision --autogenerate -m "description of changes"
alembic upgrade head
```
