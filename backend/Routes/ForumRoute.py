from fastapi import HTTPException, Request
from typing import Optional
from datetime import datetime, timezone
from bson import ObjectId
from Models import ForumModel, CommentModel
import database as db
import server as sv

# ======================= FORUM ROUTES =======================

@sv.api_router.post("/forum/posts")
async def create_forum_post(data: ForumModel, request: Request):
    user = await sv.get_current_user(request)
    
    post_doc = {
        "title": data.title,
        "content": data.content,
        "category": data.category,
        "author_id": user["_id"],
        "author_name": user["name"],
        "author_avatar": user.get("avatar_url"),
        "likes": [],
        "comments_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db.forum_posts.insert_one(post_doc)
    return {"id": str(result.inserted_id), "message": "Post created"}

@sv.api_router.get("/forum/posts")
async def list_forum_posts(
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 10
):
    query = {}
    if category:
        query["category"] = category
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"content": {"$regex": search, "$options": "i"}}
        ]
    
    skip = (page - 1) * limit
    total = await db.forum_posts.count_documents(query)
    
    posts = await db.forum_posts.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    result = []
    for post in posts:
        post["id"] = str(post["_id"])
        del post["_id"]
        post["likes_count"] = len(post.get("likes", []))
        del post["likes"]
        result.append(post)
    
    return {
        "posts": result,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }

@sv.api_router.get("/forum/posts/{post_id}")
async def get_forum_post(post_id: str, request: Request):
    try:
        post = await db.forum_posts.find_one({"_id": ObjectId(post_id)})
    except:
        raise HTTPException(status_code=404, detail="Post not found")
    
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    post["id"] = str(post["_id"])
    del post["_id"]
    post["likes_count"] = len(post.get("likes", []))
    
    # Check if current user liked
    try:
        user = await sv.get_optional_user(request)
        post["user_liked"] = user["_id"] in post.get("likes", []) if user else False
    except:
        post["user_liked"] = False
    
    del post["likes"]
    
    # Get comments
    comments = await db.forum_comments.find({"post_id": post_id}).sort("created_at", 1).to_list(100)
    post["comments"] = []
    for comment in comments:
        comment["id"] = str(comment["_id"])
        del comment["_id"]
        post["comments"].append(comment)
    
    return post

@sv.api_router.post("/forum/posts/{post_id}/comments")
async def create_comment(post_id: str, data: CommentModel, request: Request):
    user = await sv.get_current_user(request)
    
    post = await db.forum_posts.find_one({"_id": ObjectId(post_id)})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    comment_doc = {
        "post_id": post_id,
        "content": data.content,
        "author_id": user["_id"],
        "author_name": user["name"],
        "author_avatar": user.get("avatar_url"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db.forum_comments.insert_one(comment_doc)
    
    # Update comments count
    await db.forum_posts.update_one(
        {"_id": ObjectId(post_id)},
        {"$inc": {"comments_count": 1}}
    )
    
    # Notify post author
    if post["author_id"] != user["_id"]:
        await db.notifications.insert_one({
            "user_id": post["author_id"],
            "title": "Novo comentário",
            "message": f"{user['name']} comentou em seu post",
            "notification_type": "forum_reply",
            "related_id": post_id,
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
    
    return {"id": str(result.inserted_id), "message": "Comment added"}

@sv.api_router.post("/forum/posts/{post_id}/like")
async def like_post(post_id: str, request: Request):
    user = await sv.get_current_user(request)
    
    post = await db.forum_posts.find_one({"_id": ObjectId(post_id)})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    likes = post.get("likes", [])
    if user["_id"] in likes:
        # Unlike
        await db.forum_posts.update_one(
            {"_id": ObjectId(post_id)},
            {"$pull": {"likes": user["_id"]}}
        )
        return {"liked": False}
    else:
        # Like
        await db.forum_posts.update_one(
            {"_id": ObjectId(post_id)},
            {"$addToSet": {"likes": user["_id"]}}
        )
        return {"liked": True}