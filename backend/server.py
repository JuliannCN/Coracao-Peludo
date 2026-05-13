from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
from typing import Optional
from datetime import datetime, timezone, timedelta
import backend as db
import bcrypt
import jwt
from bson import ObjectId

# ======================= CONFIG =======================

JWT_ALGORITHM = "HS256"

def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]

# ======================= PASSWORD =======================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8")
    )

# ======================= JWT =======================

def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=60),
        "type": "access"
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "refresh"
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

# ======================= AUTH =======================

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")

    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])

        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")

        user = await db.users.find_one(
            {"_id": ObjectId(payload["sub"])},
            {"password_hash": 0}
        )

        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        user["_id"] = str(user["_id"])
        return user

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_optional_user(request: Request) -> Optional[dict]:
    try:
        return await get_current_user(request)
    except:
        return None

# ======================= APP =======================

app = FastAPI(title="Corações Peludos API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ajuste em produção
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter()

# ======================= LOG =======================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ======================= ROUTES IMPORT =======================

# Exemplo de estrutura:
# routes/
# ├── auth_routes.py
# ├── user_routes.py
# ├── pet_routes.py
# ├── forum_routes.py

from Routes import AuthRoute, UserRoute, PetRoute, ForumRoute, AdoptionRoute, FileRoute, MessageRoute, NotificationRoute, RootRoute, StatsRoutes

api_router.include_router(AuthRoute.router, prefix="/auth", tags=["Auth"])
api_router.include_router(UserRoute.router, prefix="/users", tags=["Users"])
api_router.include_router(PetRoute.router, prefix="/pets", tags=["Pets"])
api_router.include_router(ForumRoute.router, prefix="/forum", tags=["Forum"])
api_router.include_router(AdoptionRoute.router, prefix="/adoption", tags=["Adoption"])
api_router.include_router(FileRoute.router, prefix="/file", tags=["File"])
api_router.include_router(MessageRoute.router, prefix="/message", tags=["Message"])
api_router.include_router(NotificationRoute.router, prefix="/notification", tags=["Notification"])
api_router.include_router(RootRoute.router, prefix="/root", tags=["Root"])
api_router.include_router(StatsRoutes.router, prefix="/stats", tags=["Stats"])

# ======================= HEALTH CHECK =======================

@api_router.get("/")
async def health_check():
    return {"status": "API rodando 🚀"}

# ======================= REGISTER ROUTER =======================

app.include_router(api_router)