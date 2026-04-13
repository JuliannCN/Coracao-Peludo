from fastapi import FastAPI, APIRouter, HTTPException, Request
import os
import logging
from typing import Optional
from datetime import datetime, timezone
import jwt
import requests
from bson import ObjectId
from Models import MessageModel
import database as db
import server as sv

# ======================= MESSAGE ROUTES =======================

@sv.api_router.post("/messages")
async def send_message(data: MessageModel, request: Request):
    user = await sv.get_current_user(request)
    
    receiver = await db.users.find_one({"_id": ObjectId(data.receiver_id)})
    if not receiver:
        raise HTTPException(status_code=404, detail="Receiver not found")
    
    pet_name = None
    if data.pet_id:
        pet = await db.pets.find_one({"_id": ObjectId(data.pet_id)})
        pet_name = pet["name"] if pet else None
    
    message_doc = {
        "sender_id": user["_id"],
        "sender_name": user["name"],
        "receiver_id": data.receiver_id,
        "receiver_name": receiver["name"],
        "content": data.content,
        "pet_id": data.pet_id,
        "pet_name": pet_name,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db.messages.insert_one(message_doc)
    
    # Create notification
    await db.notifications.insert_one({
        "user_id": data.receiver_id,
        "title": "Nova mensagem",
        "message": f"Você recebeu uma mensagem de {user['name']}",
        "notification_type": "message",
        "related_id": str(result.inserted_id),
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    return {"id": str(result.inserted_id), "message": "Message sent"}

@sv.api_router.get("/messages")
async def get_messages(request: Request):
    user = await sv.get_current_user(request)
    
    # Get conversations
    messages = await db.messages.find({
        "$or": [
            {"sender_id": user["_id"]},
            {"receiver_id": user["_id"]}
        ]
    }).sort("created_at", -1).to_list(1000)
    
    # Group by conversation partner
    conversations = {}
    for msg in messages:
        partner_id = msg["receiver_id"] if msg["sender_id"] == user["_id"] else msg["sender_id"]
        partner_name = msg["receiver_name"] if msg["sender_id"] == user["_id"] else msg["sender_name"]
        
        if partner_id not in conversations:
            conversations[partner_id] = {
                "partner_id": partner_id,
                "partner_name": partner_name,
                "last_message": msg["content"],
                "last_message_time": msg["created_at"],
                "unread_count": 0
            }
        
        if msg["receiver_id"] == user["_id"] and not msg["read"]:
            conversations[partner_id]["unread_count"] += 1
    
    return list(conversations.values())

@sv.api_router.get("/messages/{partner_id}")
async def get_conversation(partner_id: str, request: Request):
    user = await sv.get_current_user(request)
    
    messages = await db.messages.find({
        "$or": [
            {"sender_id": user["_id"], "receiver_id": partner_id},
            {"sender_id": partner_id, "receiver_id": user["_id"]}
        ]
    }).sort("created_at", 1).to_list(100)
    
    # Mark as read
    await db.messages.update_many(
        {"sender_id": partner_id, "receiver_id": user["_id"], "read": False},
        {"$set": {"read": True}}
    )
    
    result = []
    for msg in messages:
        msg["id"] = str(msg["_id"])
        del msg["_id"]
        msg["is_mine"] = msg["sender_id"] == user["_id"]
        result.append(msg)
    
    return result