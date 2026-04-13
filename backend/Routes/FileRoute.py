from fastapi import HTTPException, Response, Query
from typing import Optional
import database as db
import server as sv

# ======================= FILE ROUTES =======================

@sv.api_router.get("/files/{path:path}")
async def download_file(path: str, auth: Optional[str] = Query(None)):
    record = await db.files.find_one({"storage_path": path, "is_deleted": False})
    if not record:
        # Try to get directly from storage
        try:
            data, content_type = sv.get_object(path)
            return Response(content=data, media_type=content_type)
        except:
            raise HTTPException(status_code=404, detail="File not found")
    
    data, content_type = sv.get_object(path)
    return Response(content=data, media_type=record.get("content_type", content_type))