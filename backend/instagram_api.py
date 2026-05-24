import httpx
import os
from dotenv import load_dotenv

load_dotenv()

GRAPH_API_BASE = "https://graph.facebook.com/v18.0"


async def send_dm(recipient_id: str, message: str, page_access_token: str) -> dict:
    """
    Instagram Direct Message yuborish.
    recipient_id: Foydalanuvchining Instagram IGSID yoki PSIDi
    """
    url = f"{GRAPH_API_BASE}/me/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message},
        "messaging_type": "RESPONSE"
    }
    params = {"access_token": page_access_token}

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, json=payload, params=params)
        data = response.json()
        if response.status_code != 200:
            print(f"❌ DM yuborishda xato: {data}")
        else:
            print(f"✅ DM yuborildi → {recipient_id}")
        return data


async def get_user_info(user_id: str, page_access_token: str) -> dict:
    """Foydalanuvchi ma'lumotlarini olish"""
    url = f"{GRAPH_API_BASE}/{user_id}"
    params = {
        "fields": "id,name,username",
        "access_token": page_access_token
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params=params)
        return response.json()


async def get_instagram_account_info(page_access_token: str) -> dict:
    """
    Page Access Token orqali ulangan Instagram Business akkauntini topish
    """
    url = f"{GRAPH_API_BASE}/me"
    params = {
        "fields": "id,name,instagram_business_account",
        "access_token": page_access_token
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params=params)
        page_data = response.json()

    if "instagram_business_account" not in page_data:
        return {"error": "Instagram Business akkaunt topilmadi. Facebook Page ga ulangan bo'lishi kerak."}

    ig_id = page_data["instagram_business_account"]["id"]

    # Instagram akkaunt username olish
    ig_url = f"{GRAPH_API_BASE}/{ig_id}"
    params2 = {
        "fields": "id,username,name,followers_count,media_count",
        "access_token": page_access_token
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        ig_response = await client.get(ig_url, params=params2)
        return ig_response.json()


async def get_post_info(post_id: str, page_access_token: str) -> dict:
    """Post ma'lumotlarini olish"""
    url = f"{GRAPH_API_BASE}/{post_id}"
    params = {
        "fields": "id,caption,media_type,permalink,timestamp",
        "access_token": page_access_token
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params=params)
        return response.json()


async def subscribe_to_webhooks(page_id: str, page_access_token: str, app_access_token: str) -> dict:
    """
    Instagram webhook obunasini sozlash
    Subscribed fields: comments, messages
    """
    url = f"{GRAPH_API_BASE}/{page_id}/subscribed_apps"
    params = {"access_token": page_access_token}
    payload = {
        "subscribed_fields": "comments,messages,mentions,message_reactions"
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload, params=params)
        return response.json()


async def verify_access_token(page_access_token: str) -> dict:
    """Access token tekshirish"""
    url = f"{GRAPH_API_BASE}/me"
    params = {
        "fields": "id,name",
        "access_token": page_access_token
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params=params)
        data = response.json()
        if "error" in data:
            return {"valid": False, "error": data["error"]["message"]}
        return {"valid": True, "id": data.get("id"), "name": data.get("name")}


async def reply_to_comment(comment_id: str, message: str, page_access_token: str) -> dict:
    """Kommentariyaga javob berish (ixtiyoriy)"""
    url = f"{GRAPH_API_BASE}/{comment_id}/replies"
    params = {"access_token": page_access_token}
    payload = {"message": message}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload, params=params)
        return response.json()


# ══════════════════════════════════════
#  POLLING uchun qo'shimcha funksiyalar
# ══════════════════════════════════════

async def get_user_media(ig_user_id: str, page_access_token: str, limit: int = 50) -> list:
    """Instagram akkauntning barcha media (postlar) ro'yxatini olish"""
    url = f"{GRAPH_API_BASE}/{ig_user_id}/media"
    params = {
        "fields": "id,shortcode,timestamp,media_type,permalink",
        "limit": limit,
        "access_token": page_access_token
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, params=params)
        data = response.json()
        if "error" in data:
            print(f"❌ get_user_media xatosi: {data['error'].get('message')}")
            return []
        return data.get("data", [])


async def get_media_comments(media_id: str, page_access_token: str, limit: int = 25) -> list:
    """Media postidagi kommentariyalarni olish"""
    url = f"{GRAPH_API_BASE}/{media_id}/comments"
    params = {
        "fields": "id,text,from,timestamp",
        "limit": limit,
        "access_token": page_access_token
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, params=params)
        data = response.json()
        if "error" in data:
            print(f"❌ get_media_comments xatosi ({media_id}): {data['error'].get('message')}")
            return []
        return data.get("data", [])


async def get_ig_conversations(page_id: str, page_access_token: str) -> list:
    """Instagram DM suhbatlarini olish (Page ID kerak)"""
    url = f"{GRAPH_API_BASE}/{page_id}/conversations"
    params = {
        "platform": "instagram",
        "fields": "id,participants,messages{id,message,from,created_time}",
        "limit": 10,
        "access_token": page_access_token
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, params=params)
        data = response.json()
        if "error" in data:
            print(f"❌ get_ig_conversations xatosi: {data['error'].get('message')}")
            return []
        return data.get("data", [])


async def get_page_id(page_access_token: str) -> str | None:
    """Page Access Token dan Facebook Page ID olish"""
    url = f"{GRAPH_API_BASE}/me"
    params = {"fields": "id", "access_token": page_access_token}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params=params)
        data = response.json()
        return data.get("id")
