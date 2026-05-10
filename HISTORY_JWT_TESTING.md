# Testing the History API with JWT Authentication

## Overview
The `/api/history` endpoint now uses JWT token-based authentication. The token is verified from the `Authorization: Bearer <token>` header, and all user/org/master-user info is extracted from the token claims.

---

## Complete Flow

### Step 1: Register a User
**Endpoint:** `POST /api/auth/register`

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securePassword123",
  "fullName": "John Doe",
  "orgName": "My Organization"
}
```

**Response:**
```json
{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "user": {
    "id": "user-uuid-1234",
    "email": "user@example.com",
    "name": "John Doe",
    "orgId": "org-uuid-5678",
    "masterUserId": "user-uuid-1234",
    "role": "admin"
  }
}
```

**Save the `token` for the next step.**

---

### Step 2: Fetch History with JWT Token
**Endpoint:** `POST /api/history`

**Request Headers:**
```
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
Content-Type: application/json
```

**Request Body (optional - can be empty):**
```json
{}
```

**What happens behind the scenes:**
1. Extracts the Bearer token from Authorization header
2. Verifies the JWT signature and expiration
3. Extracts claims: `sub` (user_id), `org_id`, `master_user_id`
4. Queries database to verify user still belongs to org
5. Returns all history visible to that user

**Response (for regular user):**
```json
{
  "success": true,
  "sessions": [
    {
      "session_id": "session-uuid-1",
      "query": "Connector torque failure during assembly",
      "domain": "Manufacturing",
      "title": "Assembly Line B Failure",
      "created_at": "2026-05-10T02:12:21.608Z",
      "cause_count": 5,
      "root_causes": [
        "Lack of automated maintenance alerts"
      ],
      "ishikawa": [...full Ishikawa JSON...],
      "five_whys": [...full 5-Whys JSON...]
    }
  ],
  "message": null
}
```

**Response (for master user):**
- Receives ALL sessions for the entire organization (not just their own)

---

## JWT Token Claims

The token issued at login/register contains:

```json
{
  "sub": "user-id-uuid",
  "email": "user@example.com",
  "org_id": "org-id-uuid",
  "master_user_id": "master-user-id-uuid",
  "role": "admin|user",
  "exp": 1715335941
}
```

**Key points:**
- `sub`: The user's ID (verified against database)
- `org_id`: The organization they belong to
- `master_user_id`: The org's master user ID (determines visibility level)
- `exp`: Token expiration (24 hours by default)

---

## Error Responses

### 1. Missing Authorization Header
```
Status: 401
{
  "detail": "Missing or invalid Authorization header"
}
```

### 2. Invalid or Expired Token
```
Status: 401
{
  "detail": "Invalid or expired JWT token"
}
```

### 3. Token Missing User Info
```
Status: 401
{
  "detail": "Invalid JWT token: missing user info"
}
```

### 4. Token Missing Org Claims
```
Status: 401
{
  "detail": "Invalid JWT token: missing organization info"
}
```

### 5. User Not Found in Database
```
Status: 401
{
  "detail": "User not found"
}
```

### 6. User Doesn't Belong to Org
```
Status: 403
{
  "detail": "User does not belong to this organization"
}
```

### 7. Organization Not Found
```
Status: 404
{
  "detail": "Organization not found"
}
```

---

## Testing with cURL

### 1. Register
```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "testuser@example.com",
    "password": "TestPass123!",
    "fullName": "Test User",
    "orgName": "Test Organization"
  }'
```

### 2. Get History (with token from step 1)
```bash
curl -X POST http://localhost:8000/api/history \
  -H "Authorization: Bearer <TOKEN_FROM_STEP_1>" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 3. Test without token (should fail)
```bash
curl -X POST http://localhost:8000/api/history \
  -H "Content-Type: application/json" \
  -d '{}'
```

Expected: 401 Unauthorized

---

## Testing with Python

```python
import requests
import json

BASE_URL = "http://localhost:8000"

# Step 1: Register
register_response = requests.post(
    f"{BASE_URL}/api/auth/register",
    json={
        "email": "test@example.com",
        "password": "password123",
        "fullName": "Test User",
        "orgName": "Test Org"
    }
)

data = register_response.json()
token = data["token"]

# Step 2: Get history with JWT
history_response = requests.post(
    f"{BASE_URL}/api/history",
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    },
    json={}
)

print(history_response.json())
```

---

## Key Implementation Details

### Where JWT Verification Happens
- **File:** [src/utils/auth.py](../src/utils/auth.py)
  - `get_token_claims_from_bearer()` — Extracts and validates token
  - `decode_access_token()` — Decodes JWT with signature verification
  - `extract_bearer_token()` — Safely extracts token from header

### History Route
- **File:** [src/api/root_cause/routes.py](../src/api/root_cause/routes.py#L439)
  - Verifies Bearer token
  - Extracts user/org claims
  - Validates user-org relationship against database
  - Enforces master-user visibility rules

### Security Features
✅ Token signature verification (HS256)  
✅ Token expiration check (24 hours default)  
✅ User identity cannot be spoofed (verified against DB)  
✅ Organization access control enforced  
✅ Master-user privilege levels respected  
✅ All authorization failures logged

---

## Environment Variables

```bash
JWT_SECRET=your-secret-key-change-me
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440  # 24 hours
```

**Important:** Set `JWT_SECRET` to a strong, random value in production!

