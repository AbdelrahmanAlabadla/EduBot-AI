# API Reference

Base URL: `http://localhost:8000`

Authentication: Bearer JWT token in `Authorization` header.

---

## Authentication

### POST /auth/setup

Bootstrap the first school and super_admin account. Only works once (no schools exist yet).

**Auth:** None

**Request:**
```json
{
  "school_name": "My University",
  "school_slug": "my-uni",
  "admin_name": "Super Admin",
  "admin_email": "admin@myuni.edu",
  "admin_password": "securepassword"
}
```

**Response (201):**
```json
{
  "school_id": "uuid",
  "user_id": "uuid",
  "access_token": "eyJhbGci...",
  "token_type": "bearer"
}
```

**Errors:** 400 (setup already completed)

---

### POST /auth/register

Create a new user account.

**Auth:** None

**Request:**
```json
{
  "name": "John Doe",
  "email": "john@example.com",
  "password": "securepassword",
  "school_id": "uuid-here",
  "role": "school_admin"
}
```

**Response (201):**
```json
{
  "id": "uuid",
  "school_id": "uuid",
  "name": "John Doe",
  "email": "john@example.com",
  "role": "school_admin",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

**Errors:** 409 (email already registered)

---

### POST /auth/login

Authenticate and receive a JWT token.

**Auth:** None

**Request:**
```json
{
  "email": "john@example.com",
  "password": "securepassword"
}
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJI...",
  "token_type": "bearer"
}
```

**Errors:** 401 (invalid credentials)

---

### GET /auth/me

Return the currently authenticated user.

**Auth:** Bearer token required

**Response (200):**
```json
{
  "id": "uuid",
  "school_id": "uuid",
  "name": "John Doe",
  "email": "john@example.com",
  "role": "school_admin",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

**Errors:** 401 (invalid/expired token)

---

## Schools

All school endpoints require authentication.

### POST /schools

Create a new school.

**Request:**
```json
{
  "name": "Springfield University",
  "slug": "springfield-uni",
  "email": "info@springfield.edu",
  "phone": "+1234567890",
  "language": "en",
  "status": "active"
}
```

**Response (201):** School object

**Errors:** 409 (slug already exists)

---

### GET /schools/{school_id}

Get school by ID.

**Response (200):** School object

**Errors:** 404 (not found)

---

### PUT /schools/{school_id}

Update school fields.

**Request (partial):**
```json
{
  "name": "Updated Name"
}
```

**Response (200):** Updated school object

**Errors:** 404 (not found)

---

### DELETE /schools/{school_id}

Delete a school and all its users.

**Response:** 204 No Content

**Errors:** 404 (not found)

---

## Users

All user endpoints require authentication. Users are scoped to the authenticated user's school.

### GET /users

List all users in the current school.

**Response (200):** Array of user objects

---

### POST /users

Create a staff user in the current school.

**Request:**
```json
{
  "name": "Staff Member",
  "email": "staff@example.com",
  "password": "securepassword",
  "role": "staff"
}
```

**Response (201):** User object

**Errors:** 409 (email already registered)

---

### GET /users/{user_id}

Get user by ID (scoped to current school).

**Response (200):** User object

**Errors:** 404 (not found)

---

### PUT /users/{user_id}

Update user fields.

**Request (partial):**
```json
{
  "name": "New Name",
  "role": "staff"
}
```

**Response (200):** Updated user object

**Errors:** 404 (not found)

---

### DELETE /users/{user_id}

Delete a user.

**Response:** 204 No Content

**Errors:** 404 (not found)
