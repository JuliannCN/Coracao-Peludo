from fastapi import FastAPI, APIRouter, HTTPException, Request
from starlette.middleware.cors import CORSMiddleware
import os
import logging
from datetime import datetime, timezone, timedelta
import bcrypt
from typing import Optional
import jwt
import requests
from bson import ObjectId
import database as db
import server as sv

# ======================= ROOT ROUTE =======================

@sv.api_router.get("/")
async def root():
    return {"message": "Corações Peludos API", "version": "1.0.0"}

# Include the router in the main app
sv.app.include_router(sv.api_router)

sv.app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000"), "*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup event
@sv.app.on_event("startup")
async def startup():
    # Create indexes
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.pets.create_index([("status", 1), ("created_at", -1)])
    await db.pets.create_index("ong_id")
    await db.adoptions.create_index([("user_id", 1), ("status", 1)])
    await db.adoptions.create_index([("ong_id", 1), ("status", 1)])
    await db.forum_posts.create_index([("category", 1), ("created_at", -1)])
    await db.messages.create_index([("sender_id", 1), ("receiver_id", 1)])
    await db.notifications.create_index([("user_id", 1), ("read", 1)])
    
    # Initialize storage
    try:
        sv.init_storage()
        sv.logger.info("Storage initialized")
    except Exception as e:
        sv.logger.error(f"Storage init failed: {e}")
    
    # Seed admin
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        hashed = sv.hash_password(admin_password)
        await db.users.insert_one({
            "email": admin_email,
            "password_hash": hashed,
            "name": "Admin",
            "user_type": "admin",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        sv.logger.info("Admin user created")
    elif not sv.verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": sv.hash_password(admin_password)}})
        sv.logger.info("Admin password updated")
    
    # Write test credentials
    import pathlib
    pathlib.Path("/app/memory").mkdir(parents=True, exist_ok=True)
    with open("/app/memory/test_credentials.md", "w") as f:
        f.write(f"""# Test Credentials

## Admin Account
- Email: {admin_email}
- Password: {admin_password}
- Role: admin

## Auth Endpoints
- POST /api/auth/register
- POST /api/auth/login
- POST /api/auth/logout
- GET /api/auth/me
- POST /api/auth/refresh
- POST /api/auth/google/session
""")
    sv.logger.info("Test credentials written")

@sv.app.on_event("shutdown")
async def shutdown_db_client():
    Request.client.close()