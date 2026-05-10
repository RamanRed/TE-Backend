from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel

from ..root_cause.routes import generate_problem, gen_five_why
from ..root_cause.schemas import RootCauseProblemRequest, RootCauseFiveWhyRequest
from ...database.prisma_client import get_prisma
from ...utils.auth import hash_password, verify_password, create_access_token, decode_access_token

import uuid
from slugify import slugify

router = APIRouter(tags=["compatibility"])

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    fullName: str
    orgName: str

@router.post("/api/auth/register")
async def register(request: RegisterRequest):
    """Real register endpoint using Prisma and bcrypt."""
    try:
        db = get_prisma()
        
        # Check if user already exists
        existing_user = db.user.find_unique(where={"email": request.email})
        if existing_user:
            raise HTTPException(status_code=400, detail="User with this email already exists")
            
        # 1. Create Organization
        org_id = str(uuid.uuid4())
        org_slug = slugify(request.orgName)
        
        # Ensure unique slug
        base_slug = org_slug
        counter = 1
        while db.organization.find_unique(where={"slug": org_slug}):
            org_slug = f"{base_slug}-{counter}"
            counter += 1
            
        org = db.organization.create(data={
            "id": org_id,
            "name": request.orgName,
            "slug": org_slug,
            "isActive": True
        })
        
        # 2. Create User
        user_id = str(uuid.uuid4())
        hashed_password = hash_password(request.password)
        
        user = db.user.create(data={
            "id": user_id,
            "orgId": org_id,
            "email": request.email,
            "password": hashed_password,
            "fullName": request.fullName,
            "role": "admin", # First user is admin
            "isMasterUser": True, # First user of new org is master user
            "isActive": True
        })
        
        # 3. Update Organization with masterUserId
        db.organization.update(
            where={"id": org_id},
            data={"masterUserId": user_id}
        )
        
        # 4. Create JWT token with the claims needed by authenticated routes
        token = create_access_token(data={
            "sub": user_id,
            "email": request.email,
            "org_id": org_id,
            "master_user_id": user_id,
            "role": "admin",
        })
        
        return {
            "token": token,
            "user": {
                "id": user_id,
                "email": request.email,
                "name": request.fullName,
                "orgId": org_id,
                "masterUserId": user_id, # The creator is the master user
                "role": "admin"
            }
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

@router.post("/api/auth/login")
async def login(request: LoginRequest):
    """Real login endpoint using Prisma and bcrypt."""
    try:
        print(f"Attempting login for email: {request.email}")
        db = get_prisma()
        # Find user by email
        print(f"Looking up user by email: {request.email}")
        user = db.user.find_unique(where={"email": request.email})
        
        if not user or not user.password:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Verify password
        if not verify_password(request.password, user.password):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Fetch org to get masterUserId
        org = db.organization.find_unique(where={"id": user.orgId})
        master_user_id = org.masterUserId if org else None

        # Create JWT token with the claims needed by authenticated routes
        token = create_access_token(data={
            "sub": user.id,
            "email": user.email,
            "org_id": user.orgId,
            "master_user_id": master_user_id,
            "role": user.role,
        })

        return {
            "token": token,
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.fullName,
                "orgId": user.orgId,
                "masterUserId": master_user_id,
                "role": user.role
            }
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@router.get("/api/auth/verify")
async def verify(authorization: Optional[str] = Header(None)):
    """Real verify endpoint using JWT."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    
    token = authorization.split(" ")[1]
    payload = decode_access_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    user_id = payload.get("sub")
    try:
        db = get_prisma()
        user = db.user.find_unique(where={"id": user_id})
        
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
            
        # Fetch org to get masterUserId
        org = db.organization.find_unique(where={"id": user.orgId})
        master_user_id = org.masterUserId if org else None

        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.fullName,
                "orgId": user.orgId,
                "masterUserId": master_user_id,
                "role": user.role
            }
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")

@router.post("/api/auth/logout")
async def logout():
    """Logout endpoint."""
    return {"success": True}

@router.post("/generate")
async def generate_alias(request: RootCauseProblemRequest):
    """Alias for /api/problem to support legacy frontend routes."""
    return await generate_problem(request)

@router.post("/generate-five-why")
async def generate_five_why_alias(request: RootCauseFiveWhyRequest):
    """Alias for /api/gen-five-why to support legacy frontend routes."""
    return await gen_five_why(request)
