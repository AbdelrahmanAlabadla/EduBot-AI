# Development Notes

## Architecture Decisions

### Why PostgreSQL?

- Academic institutions commonly use PostgreSQL.
- JSONB support for future flexible field storage.
- Excellent full-text search capabilities (useful for document search later).
- Strong concurrency support for multi-tenant workloads.

### Why SQLAlchemy?

- De facto standard Python ORM.
- Database-agnostic (could switch to SQLite for testing).
- Mature, well-documented, excellent Alembic integration.
- 2.0 style provides modern type-safe querying.

### Why Alembic?

- Version-controlled database migrations.
- Auto-generation from model changes reduces human error.
- Rollback support for safe deployments.
- Industry standard alongside SQLAlchemy.

### Multi-Tenant Architecture

The current approach is **single database, shared schema with school_id isolation**:
- All records are tagged with `school_id`.
- Queries filter by `school_id` of the authenticated user.
- Simple to implement and deploy.
- Suitable for hundreds of schools on a single database.

If scale demands it, this can evolve to:
- **Schema-per-tenant**: Separate PostgreSQL schemas per school.
- **Database-per-tenant**: Separate databases.

### Why Not Async?

Current implementation uses synchronous SQLAlchemy. Async can be added later with `asyncpg` + `asyncio` if the API needs higher concurrency.

## Lessons Learned

### passlib / bcrypt Compatibility

`passlib` (v1.7.4) is incompatible with `bcrypt >= 4.1`. The `passlib` library is no longer actively maintained. We use `bcrypt` directly for password hashing instead of `passlib`'s `CryptContext`.

### pydantic-settings .env path

When using `pydantic-settings`, the `env_file` path is relative to the file's location. For `app/core/config.py`, the correct path to `backend/.env` is `parents[2]`.

## Future Plans

1. **Async migration**: Switch to `asyncpg` + async SQLAlchemy for better performance.
2. **Rate limiting**: Protect public endpoints from abuse.
3. **RBAC**: Implement granular role-based access control.
4. **Audit logging**: Track changes to schools and users.
5. **Caching**: Redis for frequently accessed data.
6. **RAG pipeline**: Document processing with Qdrant vector database.
7. **Chatbot**: AI-powered chatbot for educational Q&A.
8. **File storage**: S3/MinIO for document uploads.
