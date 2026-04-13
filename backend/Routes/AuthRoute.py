from fastapi import HTTPException, Request, Response
from datetime import datetime, timezone, timedelta
import jwt
from bson import ObjectId
import backend as db
import server as sv
from Models import UserModel

# ======================= AUTH ROUTES =======================

@sv.api_router.post("/auth/register")
async def register(user_data: UserModel, response: Response):
    # Check if email exists
    existing = await db.users.find_one({"email": user_data.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user document
    user_doc = {
        "name": user_data.name,
        "email": user_data.email.lower(),
        "password_hash": sv.hash_password(user_data.password),
        "user_type": user_data.user_type,
        "phone": user_data.phone,
        "address": user_data.address,
        "city": user_data.city,
        "state": user_data.state,
        "avatar_url": None,
        "favorites": [],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Add ONG specific fields
    if user_data.user_type == "ong":
        user_doc["ong_name"] = user_data.ong_name
        user_doc["cnpj"] = user_data.cnpj
        user_doc["description"] = user_data.description
    
    result = await db.users.insert_one(user_doc)
    user_id = str(result.inserted_id)
    
    # Create tokens
    access_token = sv.create_access_token(user_id, user_data.email.lower())
    refresh_token = sv.create_refresh_token(user_id)
    
    # Set cookies
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=True, samesite="none", max_age=3600, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=True, samesite="none", max_age=604800, path="/")
    
    return {
        "id": user_id,
        "name": user_data.name,
        "email": user_data.email.lower(),
        "user_type": user_data.user_type,
        "ong_name": user_data.ong_name if user_data.user_type == "ong" else None,
        "token": access_token
    }

@sv.api_router.post("/auth/login")
async def login(credentials: UserModel, request: Request, response: Response):
    email = credentials.email.lower()
    
    # Check brute force
    ip = request.client.host if request.client else "unknown"
    identifier = f"{ip}:{email}"
    attempt = await db.login_attempts.find_one({"identifier": identifier})
    
    if attempt and attempt.get("count", 0) >= 5:
        lockout_until = attempt.get("lockout_until")
        if lockout_until:
            if isinstance(lockout_until, str):
                lockout_until = datetime.fromisoformat(lockout_until)
            if lockout_until.tzinfo is None:
                lockout_until = lockout_until.replace(tzinfo=timezone.utc)
            if lockout_until > datetime.now(timezone.utc):
                raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
    
    # Find user
    user = await db.users.find_one({"email": email})
    if not user:
        # Increment failed attempts
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {"$inc": {"count": 1}, "$set": {"lockout_until": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}},
            upsert=True
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Verify password
    if not sv.verify_password(credentials.password, user["password_hash"]):
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {"$inc": {"count": 1}, "$set": {"lockout_until": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}},
            upsert=True
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Clear failed attempts
    await db.login_attempts.delete_one({"identifier": identifier})
    
    user_id = str(user["_id"])
    access_token = sv.create_access_token(user_id, email)
    refresh_token = sv.create_refresh_token(user_id)
    
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=True, samesite="none", max_age=3600, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=True, samesite="none", max_age=604800, path="/")
    
    return {
        "id": user_id,
        "name": user["name"],
        "email": user["email"],
        "user_type": user["user_type"],
        "ong_name": user.get("ong_name"),
        "avatar_url": user.get("avatar_url"),
        "token": access_token
    }

@sv.api_router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")
    return {"message": "Logged out successfully"}

@sv.api_router.get("/auth/me")
async def get_me(request: Request):
    user = await sv.get_current_user(request)
    return {
        "id": user["_id"],
        "name": user["name"],
        "email": user["email"],
        "user_type": user["user_type"],
        "phone": user.get("phone"),
        "address": user.get("address"),
        "city": user.get("city"),
        "state": user.get("state"),
        "avatar_url": user.get("avatar_url"),
        "ong_name": user.get("ong_name"),
        "cnpj": user.get("cnpj"),
        "description": user.get("description"),
        "favorites": user.get("favorites", [])
    }

@sv.api_router.post("/auth/refresh")
async def refresh_token(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, sv.get_jwt_secret(), algorithms=[sv.JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        new_access = sv.create_access_token(str(user["_id"]), user["email"])
        response.set_cookie(key="access_token", value=new_access, httponly=True, secure=True, samesite="none", max_age=3600, path="/")
        return {"token": new_access}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")