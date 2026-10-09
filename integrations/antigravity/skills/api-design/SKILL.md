---
name: api-design
description: REST API design patterns including resource naming, HTTP status codes, pagination (cursor and offset), filtering, sorting, error envelopes, versioning, and rate limiting for production APIs. Use when designing or reviewing API endpoints.
version: 2.0.0
triggers:
  - "api design"
  - "rest api"
  - "resource naming"
  - "pagination"
  - "status codes"
  - "api versioning"
metadata:
  origin: ECC
  adapted_for: Kortext
---

# REST API Design Patterns

Conventions and best practices for designing consistent, scalable, and developer-friendly REST APIs.

## When to Activate

- Designing new REST or HTTP API endpoints
- Reviewing existing API contracts and JSON schemas
- Adding pagination (cursor or offset), filtering, or sorting
- Structuring error handling and error response envelopes
- Planning API versioning and deprecation strategies
- Building public, mobile, or partner-facing APIs

---

## Resource Design

### URL Structure

```
# Resources are nouns, plural, lowercase, kebab-case
GET    /api/v1/users
GET    /api/v1/users/:id
POST   /api/v1/users
PUT    /api/v1/users/:id
PATCH  /api/v1/users/:id
DELETE /api/v1/users/:id

# Sub-resources for parent-child relationships
GET    /api/v1/users/:id/orders
POST   /api/v1/users/:id/orders

# Actions that do not map cleanly to CRUD (use verbs sparingly)
POST   /api/v1/orders/:id/cancel
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
```

### Naming Rules

```
# GOOD
/api/v1/team-members          # kebab-case for multi-word resources
/api/v1/orders?status=active  # query params for filtering
/api/v1/users/123/orders      # nested resources for ownership

# BAD
/api/v1/getUsers              # verb in URL
/api/v1/user                  # singular (use plural)
/api/v1/team_members          # snake_case in URLs
/api/v1/users/123/getOrders   # verb in nested resource
```

---

## HTTP Methods and Status Codes

### Method Semantics

| Method | Idempotent | Safe | Use For |
|--------|-----------|------|---------|
| **GET** | Yes | Yes | Retrieve resources (no state changes) |
| **POST** | No | No | Create resources, execute non-idempotent actions |
| **PUT** | Yes | No | Complete replacement of a resource |
| **PATCH** | No* | No | Partial update of specific resource fields |
| **DELETE** | Yes | No | Remove a resource |

*PATCH can be implemented idempotently.

### Status Code Reference

```
# Success
200 OK - GET, PUT, PATCH (with response body)
201 Created - POST (always include Location header)
204 No Content - DELETE, PUT (no response body)

# Client Errors
400 Bad Request - Validation failure, malformed JSON
401 Unauthorized - Missing or invalid authentication token
403 Forbidden - Authenticated but lacking permission
404 Not Found - Requested resource does not exist
409 Conflict - State conflict or duplicate unique key
422 Unprocessable Entity - Semantically invalid payload (schema validation failed)
429 Too Many Requests - Rate limit exceeded

# Server Errors
500 Internal Server Error - Unexpected unhandled failure (never leak stack traces)
502 Bad Gateway - Upstream microservice or database connection failed
503 Service Unavailable - Server overloaded or undergoing maintenance (include Retry-After)
```

### Common Status Code Anti-Patterns

```
# BAD: Returning 200 OK for errors
{ "status": 200, "success": false, "error": "Not found" }

# GOOD: Return 404 Not Found with error body
HTTP/1.1 404 Not Found
{ "error": { "code": "not_found", "message": "User not found" } }

# BAD: Returning 200 for newly created resources without Location
# GOOD: Return 201 Created with Location header
HTTP/1.1 201 Created
Location: /api/v1/users/abc-123
```

---

## Response Envelopes

### Success Single Resource

```json
{
  "data": {
    "id": "usr_abc123",
    "email": "alice@example.com",
    "name": "Alice Smith",
    "created_at": "2026-01-15T10:30:00Z"
  }
}
```

### Collection Response with Pagination

```json
{
  "data": [
    { "id": "usr_abc123", "name": "Alice Smith" },
    { "id": "usr_def456", "name": "Bob Jones" }
  ],
  "meta": {
    "total": 142,
    "page": 1,
    "per_page": 20,
    "total_pages": 8
  },
  "links": {
    "self": "/api/v1/users?page=1&per_page=20",
    "next": "/api/v1/users?page=2&per_page=20",
    "last": "/api/v1/users?page=8&per_page=20"
  }
}
```

### Structured Error Response

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": [
      {
        "field": "email",
        "message": "Must be a valid email address",
        "code": "invalid_format"
      },
      {
        "field": "age",
        "message": "Must be between 0 and 150",
        "code": "out_of_range"
      }
    ]
  }
}
```

---

## Pagination Patterns

### 1. Offset-Based Pagination (Simple)

```
GET /api/v1/users?page=2&per_page=20

SQL:
SELECT * FROM users ORDER BY created_at DESC LIMIT 20 OFFSET 20;
```
- **Best For:** Admin dashboards, search results where jumping to page N is expected.
- **Drawback:** Degrades at high offsets (`OFFSET 100000`); inconsistent when rows are inserted concurrently.

### 2. Cursor-Based Pagination (Scalable)

```
GET /api/v1/users?cursor=eyJpZCI6MTIzfQ&limit=20

SQL:
SELECT * FROM users WHERE id > :cursor_id ORDER BY id ASC LIMIT 21;
```

```json
{
  "data": [...],
  "meta": {
    "has_next": true,
    "next_cursor": "eyJpZCI6MTQzfQ"
  }
}
```
- **Best For:** Infinite scrolls, activity feeds, high-scale public APIs.
- **Benefit:** Constant-time query performance ($O(1)$ index seek); impervious to concurrent row insertions.

---

## Filtering, Sorting, and Search

### Filtering
```
# Exact matching
GET /api/v1/orders?status=active&customer_id=usr_123

# Comparison operators via bracket notation
GET /api/v1/products?price[gte]=10&price[lte]=100
GET /api/v1/orders?created_at[after]=2026-01-01

# Multiple values (comma-separated)
GET /api/v1/products?category=electronics,books
```

### Sorting
```
# Single field (prefix - for descending)
GET /api/v1/products?sort=-created_at

# Multi-field sorting
GET /api/v1/products?sort=-featured,price,-created_at
```

### Sparse Fieldsets
```
# Retrieve only specified fields
GET /api/v1/users?fields=id,name,email
```

---

## Rate Limiting Headers

```
HTTP/1.1 200 OK
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1774000000

# When limit is exceeded
HTTP/1.1 429 Too Many Requests
Retry-After: 60
{
  "error": {
    "code": "rate_limit_exceeded",
    "message": "Rate limit exceeded. Try again in 60 seconds."
  }
}
```

---

## Versioning Strategies

### URL Path Versioning (Recommended)
```
/api/v1/users
/api/v2/users
```
- **Rule 1:** Maintain at most 2 active versions concurrently (current + previous).
- **Rule 2:** Non-breaking changes (new optional fields, new endpoints) do NOT bump the version.
- **Rule 3:** Breaking changes (renaming fields, dropping endpoints) require a version bump.
- **Rule 4:** Return `Sunset: <date>` HTTP headers on deprecated versions before returning `410 Gone`.

---

## Implementation Example: Python FastAPI

```python
from fastapi import FastAPI, Query, HTTPException, status
from pydantic import BaseModel, Field
from typing import Generic, TypeVar

T = TypeVar("T")

class MetaPagination(BaseModel):
    total: int
    page: int
    per_page: int

class CollectionResponse(BaseModel, Generic[T]):
    data: list[T]
    meta: MetaPagination

class UserOut(BaseModel):
    id: str
    name: str
    email: str

@app.get(
    "/api/v1/users",
    response_model=CollectionResponse[UserOut],
    status_code=status.HTTP_200_OK
)
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = None
):
    users, total = await user_service.get_paginated(page=page, per_page=per_page, status=status)
    return CollectionResponse(
        data=users,
        meta=MetaPagination(total=total, page=page, per_page=per_page)
    )
```

---

## API Design Checklist

- [ ] Resource paths use plural nouns in lowercase kebab-case (`/api/v1/team-members`).
- [ ] Correct HTTP methods used semantically (GET for read, POST for create, DELETE for remove).
- [ ] Appropriate status codes returned (201 with `Location`, 422 for schema failures).
- [ ] Strict schema validation enforced on all request bodies.
- [ ] Standardized error envelopes `{ error: { code, message, details } }`.
- [ ] Pagination implemented on all collection endpoints (default limit $\le 100$).
- [ ] Authentication required and validated before authorization checks.
- [ ] Rate limiting configured with standard headers.
- [ ] No internal implementation details or stack traces exposed to clients.
- [ ] Versioning established via URL path (`/api/v1/`).
