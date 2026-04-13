import database as db
import server as sv

# ======================= STATS ROUTES =======================

@sv.api_router.get("/stats")
async def get_stats():
    pets_available = await db.pets.count_documents({"status": "available"})
    pets_adopted = await db.pets.count_documents({"status": "adopted"})
    ongs_count = await db.users.count_documents({"user_type": "ong"})
    users_count = await db.users.count_documents({"user_type": "user"})
    
    return {
        "pets_available": pets_available,
        "pets_adopted": pets_adopted,
        "ongs_count": ongs_count,
        "users_count": users_count
    }