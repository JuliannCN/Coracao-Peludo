from fastapi import FastAPI, APIRouter, HTTPException, Request
import os
import logging
from typing import Optional
import jwt
import requests
from bson import ObjectId
import database as db
import server as sv

# ======================= NOTIFICATION ROUTES =======================

@sv.api_router.get("/notifications")
async def get_notifications(request: Request, unread_only: bool = False):
    user = await sv.get_current_user(request)
    
    query = {"user_id": user["_id"]}
    if unread_only:
        query["read"] = False
    
    notifications = await db.notifications.find(query).sort("created_at", -1).limit(50).to_list(50)
    
    result = []
    for notif in notifications:
        notif["id"] = str(notif["_id"])
        del notif["_id"]
        result.append(notif)
    
    return result

@sv.api_router.put("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, request: Request):
    user = await sv.get_current_user(request)
    
    await db.notifications.update_one(
        {"_id": ObjectId(notification_id), "user_id": user["_id"]},
        {"$set": {"read": True}}
    )
    
    return {"message": "Marked as read"}

@sv.api_router.put("/notifications/read-all")
async def mark_all_notifications_read(request: Request):
    user = await sv.get_current_user(request)
    
    await db.notifications.update_many(
        {"user_id": user["_id"], "read": False},
        {"$set": {"read": True}}
    )
    
    return {"message": "All marked as read"}