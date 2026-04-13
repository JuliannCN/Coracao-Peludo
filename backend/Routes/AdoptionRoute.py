from fastapi import HTTPException, Request
from datetime import datetime, timezone
from bson import ObjectId
from Models import AdoptionModel
import database as db
import server as sv

# ======================= ADOPTION ROUTES =======================

@sv.api_router.post("/adoptions")
async def create_adoption_request(data: AdoptionModel, request: Request):
    user = await sv.get_current_user(request)
    
    pet = await db.pets.find_one({"_id": ObjectId(data.pet_id)})
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found")
    
    if pet["status"] != "available":
        raise HTTPException(status_code=400, detail="Pet is not available for adoption")
    
    # Check if already requested
    existing = await db.adoptions.find_one({
        "pet_id": data.pet_id,
        "user_id": user["_id"],
        "status": "pending"
    })
    if existing:
        raise HTTPException(status_code=400, detail="You already have a pending request for this pet")
    
    adoption_doc = {
        "pet_id": data.pet_id,
        "pet_name": pet["name"],
        "user_id": user["_id"],
        "user_name": user["name"],
        "user_email": user["email"],
        "ong_id": pet["ong_id"],
        "message": data.message,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db.adoptions.insert_one(adoption_doc)
    
    # Create notification for ONG
    await db.notifications.insert_one({
        "user_id": pet["ong_id"],
        "title": "Nova solicitação de adoção",
        "message": f"{user['name']} quer adotar {pet['name']}",
        "notification_type": "adoption_request",
        "related_id": str(result.inserted_id),
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    return {"id": str(result.inserted_id), "message": "Adoption request sent"}

@sv.api_router.get("/adoptions/user")
async def get_user_adoptions(request: Request):
    user = await sv.get_current_user(request)
    adoptions = await db.adoptions.find({"user_id": user["_id"]}).sort("created_at", -1).to_list(100)
    
    result = []
    for adoption in adoptions:
        adoption["id"] = str(adoption["_id"])
        del adoption["_id"]
        # Get pet info
        pet = await db.pets.find_one({"_id": ObjectId(adoption["pet_id"])})
        if pet:
            adoption["pet_photo"] = pet.get("photos", [None])[0] if pet.get("photos") else None
        result.append(adoption)
    
    return result

@sv.api_router.get("/adoptions/ong")
async def get_ong_adoptions(request: Request):
    user = await sv.get_current_user(request)
    if user["user_type"] not in ["ong", "admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    adoptions = await db.adoptions.find({"ong_id": user["_id"]}).sort("created_at", -1).to_list(100)
    
    result = []
    for adoption in adoptions:
        adoption["id"] = str(adoption["_id"])
        del adoption["_id"]
        # Get pet info
        pet = await db.pets.find_one({"_id": ObjectId(adoption["pet_id"])})
        if pet:
            adoption["pet_photo"] = pet.get("photos", [None])[0] if pet.get("photos") else None
        result.append(adoption)
    
    return result

@sv.api_router.put("/adoptions/{adoption_id}")
async def update_adoption_status(adoption_id: str, request: Request):
    user = await sv.get_current_user(request)
    body = await request.json()
    status = body.get("status")
    
    if status not in ["approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    adoption = await db.adoptions.find_one({"_id": ObjectId(adoption_id)})
    if not adoption:
        raise HTTPException(status_code=404, detail="Adoption request not found")
    
    if adoption["ong_id"] != user["_id"] and user["user_type"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    
    await db.adoptions.update_one(
        {"_id": ObjectId(adoption_id)},
        {"$set": {"status": status}}
    )
    
    # If approved, update pet status
    if status == "approved":
        await db.pets.update_one(
            {"_id": ObjectId(adoption["pet_id"])},
            {"$set": {"status": "adopted"}}
        )
        # Reject other pending requests for this pet
        await db.adoptions.update_many(
            {"pet_id": adoption["pet_id"], "status": "pending", "_id": {"$ne": ObjectId(adoption_id)}},
            {"$set": {"status": "rejected"}}
        )
    
    # Create notification for user
    await db.notifications.insert_one({
        "user_id": adoption["user_id"],
        "title": "Atualização da solicitação de adoção",
        "message": f"Sua solicitação para adotar {adoption['pet_name']} foi {'aprovada' if status == 'approved' else 'rejeitada'}",
        "notification_type": "adoption_request",
        "related_id": adoption_id,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    return {"message": f"Adoption request {status}"}