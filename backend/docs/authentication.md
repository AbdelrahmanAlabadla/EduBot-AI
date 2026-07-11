# Authentication

## How JWT Authentication Works

EduBot uses stateless JWT (JSON Web Token) authentication.

### Login Flow

```
User enters email + password
         │
         ▼
Password hashed with bcrypt → compared with stored hash
         │
    ┌────┴────┐
    │         │
  Match    No Match
    │         │
    │     401 Unauthorized
    │
    ▼
JWT token created with:
  - sub: user UUID
  - exp: expiration timestamp
  - iat: issued at
         │
         ▼
Token returned to client
         │
         ▼
Client stores token and sends it in:
  Authorization: Bearer <token>
```

### Token Validation

On every protected request:

1. Server extracts token from `Authorization: Bearer <token>` header.
2. Decodes and verifies the JWT signature using `JWT_SECRET_KEY`.
3. Checks expiration (`exp` claim).
4. Extracts `sub` (user ID) from payload.
5. Fetches user from database.
6. Returns user object or 401.

## Password Hashing

- Algorithm: **bcrypt** (via the `bcrypt` Python package).
- Each password is salted automatically (bcrypt embeds the salt in the hash).
- Hash format: `$2b$<rounds>$<salt><hash>`

## Configuration

| Variable | Description |
|---|---|
| `JWT_SECRET_KEY` | Secret used to sign and verify tokens |
| `JWT_ALGORITHM` | Signing algorithm (HS256) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token lifetime in minutes (default: 60) |

## User Roles

| Role | Description |
|---|---|
| `super_admin` | Platform-wide administrator (can manage all schools) |
| `school_admin` | School-level administrator (manages users and settings) |
| `staff` | Regular staff member (limited permissions) |

The role system is currently a string field. Future iterations should implement a proper permission/authorization system with granular access control.
