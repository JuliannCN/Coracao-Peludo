from fastapi import Request, File, UploadFile
import uuid
from datetime import datetime, timezone
from bson import ObjectId
import database as db
import server as sv

# ======================= USER ROUTES =======================
@sv.api_router.put("/users/profile")
async def update_profile(request: Request):
    user = await sv.get_current_user(request)
    body = await request.json()
    
    update_fields = {}
    allowed_fields = ["name", "phone", "address", "city", "state", "ong_name", "description"]
    for field in allowed_fields:
        if field in body:
            update_fields[field] = body[field]
    
    if update_fields:
        await db.users.update_one({"_id": ObjectId(user["_id"])}, {"$set": update_fields})
    
    return {"message": "Profile updated"}

@sv.api_router.post("/users/avatar")
async def upload_avatar(request: Request, file: UploadFile = File(...)):
    user = await sv.get_current_user(request)
    
    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    path = f"{sv.APP_NAME}/avatars/{user['_id']}/{uuid.uuid4()}.{ext}"
    
    data = await file.read()
    result = sv.put_object(path, data, file.content_type or "image/jpeg")
    
    # Save to files collection
    await db.files.insert_one({
        "id": str(uuid.uuid4()),
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": file.content_type,
        "size": result.get("size", len(data)),
        "user_id": user["_id"],
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    # Update user avatar
    await db.users.update_one({"_id": ObjectId(user["_id"])}, {"$set": {"avatar_url": result["path"]}})
    
    return {"path": result["path"]}

@sv.api_router.post("/users/favorites/{pet_id}")
async def add_favorite(pet_id: str, request: Request):
    user = await sv.get_current_user(request)
    await db.users.update_one(
        {"_id": ObjectId(user["_id"])},
        {"$addToSet": {"favorites": pet_id}}
    )
    return {"message": "Added to favorites"}

@sv.api_router.delete("/users/favorites/{pet_id}")
async def remove_favorite(pet_id: str, request: Request):
    user = await sv.get_current_user(request)
    await db.users.update_one(
        {"_id": ObjectId(user["_id"])},
        {"$pull": {"favorites": pet_id}}
    )
    return {"message": "Removed from favorites"}

@sv.api_router.get("/users/favorites")
async def get_favorites(request: Request):
    user = await sv.get_current_user(request)
    favorites = user.get("favorites", [])
    if not favorites:
        return []
    
    pets = []
    for pet_id in favorites:
        try:
            pet = await db.pets.find_one({"_id": ObjectId(pet_id)}, {"_id": 0})
            if pet:
                pet["id"] = pet_id
                pets.append(pet)
        except:
            continue
    
    return pets