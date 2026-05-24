"""
Instagram Chatbot Backend — FastAPI
=====================================
Webhook → kommentariya trigger → auto DM yuborish
Admin Panel API
"""

import os
import json
import hmac
import hashlib
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
import asyncio

from database import (
    init_db, get_stats,
    get_accounts, create_account, delete_account,
    get_triggers, create_trigger, update_trigger, delete_trigger, find_matching_trigger,
    get_posts, add_post, toggle_post_monitoring,
    get_subscribers,
    upsert_subscriber,
    log_message, get_messages_log,
)
from instagram_api import (
    send_dm, get_instagram_account_info,
    get_post_info, verify_access_token, subscribe_to_webhooks
)

load_dotenv()

WEBHOOK_VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN", "my_secret_verify_token_123")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

app = FastAPI(title="Instagram Chatbot Admin", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Frontend static fayllar — absolute path bilan
import os as _os
_base = _os.path.abspath(_os.path.dirname(__file__))
frontend_path = _os.path.join(_base, "..", "frontend")
_static_dir = _os.path.abspath(_os.path.join(frontend_path, "static"))
if _os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")
else:
    print(f"⚠️ Static dir topilmadi: {_static_dir}")


@app.on_event("startup")
async def startup():
    await init_db()
    print("🚀 Instagram Chatbot server ishga tushdi!")
    print(f"📊 Admin Panel: http://localhost:{os.getenv('PORT', 8000)}")


# ════════════════════════════════════════════════
#  ADMIN PANEL — HTML sahifa
# ════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def admin_panel():
    html_file = _os.path.join(frontend_path, "index.html")
    with open(html_file, "r", encoding="utf-8") as f:
        return f.read()


# ════════════════════════════════════════════════
#  AUTH
# ════════════════════════════════════════════════

def check_admin(x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Noto'g'ri parol")
    return True


class LoginRequest(BaseModel):
    password: str


@app.post("/api/login")
async def login(req: LoginRequest):
    if req.password == ADMIN_PASSWORD:
        return {"success": True, "token": ADMIN_PASSWORD}
    raise HTTPException(status_code=401, detail="Noto'g'ri parol")


# ════════════════════════════════════════════════
#  STATS
# ════════════════════════════════════════════════

@app.get("/api/stats")
async def api_stats(auth=Depends(check_admin)):
    return await get_stats()


# ════════════════════════════════════════════════
#  ACCOUNTS
# ════════════════════════════════════════════════

class AccountCreate(BaseModel):
    page_access_token: str


@app.get("/api/accounts")
async def api_get_accounts(auth=Depends(check_admin)):
    return await get_accounts()


@app.post("/api/accounts")
async def api_create_account(body: AccountCreate, auth=Depends(check_admin)):
    # Token ni tekshirish
    verify = await verify_access_token(body.page_access_token)
    if not verify.get("valid"):
        raise HTTPException(status_code=400, detail=f"Token noto'g'ri: {verify.get('error', 'Noma\'lum xato')}")

    # Instagram akkaunt ma'lumotlarini olish
    ig_info = await get_instagram_account_info(body.page_access_token)
    if "error" in ig_info:
        raise HTTPException(status_code=400, detail=ig_info["error"])

    account = await create_account(
        instagram_id=ig_info.get("id"),
        username=ig_info.get("username", ig_info.get("name", "Unknown")),
        page_access_token=body.page_access_token
    )
    return account


@app.delete("/api/accounts/{account_id}")
async def api_delete_account(account_id: int, auth=Depends(check_admin)):
    await delete_account(account_id)
    return {"success": True}


@app.post("/api/accounts/{account_id}/verify-token")
async def api_verify_token(account_id: int, auth=Depends(check_admin)):
    accounts = await get_accounts()
    account = next((a for a in accounts if a["id"] == account_id), None)
    if not account:
        raise HTTPException(status_code=404, detail="Akkaunt topilmadi")
    result = await verify_access_token(account["page_access_token"])
    return result


# ════════════════════════════════════════════════
#  TRIGGERS
# ════════════════════════════════════════════════

class TriggerCreate(BaseModel):
    account_id: int
    keyword: str
    reply_message: str


class TriggerUpdate(BaseModel):
    keyword: str
    reply_message: str
    is_active: int = 1


@app.get("/api/triggers")
async def api_get_triggers(account_id: Optional[int] = None, auth=Depends(check_admin)):
    return await get_triggers(account_id)


@app.post("/api/triggers")
async def api_create_trigger(body: TriggerCreate, auth=Depends(check_admin)):
    trigger_id = await create_trigger(body.account_id, body.keyword, body.reply_message)
    return {"id": trigger_id, "success": True}


@app.put("/api/triggers/{trigger_id}")
async def api_update_trigger(trigger_id: int, body: TriggerUpdate, auth=Depends(check_admin)):
    await update_trigger(trigger_id, body.keyword, body.reply_message, body.is_active)
    return {"success": True}


@app.delete("/api/triggers/{trigger_id}")
async def api_delete_trigger(trigger_id: int, auth=Depends(check_admin)):
    await delete_trigger(trigger_id)
    return {"success": True}


# ════════════════════════════════════════════════
#  POSTS
# ════════════════════════════════════════════════

class PostAdd(BaseModel):
    account_id: int
    post_url: str
    caption: Optional[str] = ""


@app.get("/api/posts")
async def api_get_posts(account_id: Optional[int] = None, auth=Depends(check_admin)):
    return await get_posts(account_id)


@app.post("/api/posts")
async def api_add_post(body: PostAdd, auth=Depends(check_admin)):
    # Post ID ni URL dan ajratib olish
    # instagram.com/p/{POST_ID}/ yoki instagram.com/reel/{POST_ID}/
    import re
    match = re.search(r'instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)', body.post_url)
    if not match:
        raise HTTPException(status_code=400, detail="Noto'g'ri Instagram post URL. Format: https://instagram.com/p/XXXXX/")

    post_shortcode = match.group(1)
    await add_post(body.account_id, post_shortcode, body.post_url, body.caption)
    return {"success": True, "post_id": post_shortcode}


@app.patch("/api/posts/{post_id}/toggle")
async def api_toggle_post(post_id: int, is_monitoring: int, auth=Depends(check_admin)):
    await toggle_post_monitoring(post_id, is_monitoring)
    return {"success": True}


@app.delete("/api/posts/{post_id}")
async def api_delete_post(post_id: int, auth=Depends(check_admin)):
    from database import get_db
    db = await get_db()
    try:
        await db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        await db.commit()
    finally:
        await db.close()
    return {"success": True}


# ════════════════════════════════════════════════
#  SUBSCRIBERS
# ════════════════════════════════════════════════

@app.get("/api/subscribers")
async def api_get_subscribers(account_id: Optional[int] = None, auth=Depends(check_admin)):
    return await get_subscribers(account_id)


# ════════════════════════════════════════════════
#  MESSAGES LOG
# ════════════════════════════════════════════════

@app.get("/api/messages")
async def api_get_messages(account_id: Optional[int] = None, limit: int = 100, auth=Depends(check_admin)):
    return await get_messages_log(account_id, limit)


# ════════════════════════════════════════════════
#  TEST DM YUBORISH
# ════════════════════════════════════════════════

class TestDMRequest(BaseModel):
    account_id: int
    recipient_id: str
    message: str


@app.post("/api/test-dm")
async def api_test_dm(body: TestDMRequest, auth=Depends(check_admin)):
    accounts = await get_accounts()
    account = next((a for a in accounts if a["id"] == body.account_id), None)
    if not account:
        raise HTTPException(status_code=404, detail="Akkaunt topilmadi")

    result = await send_dm(body.recipient_id, body.message, account["page_access_token"])
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"]["message"])
    return {"success": True, "result": result}


# ════════════════════════════════════════════════
#  INSTAGRAM WEBHOOK
# ════════════════════════════════════════════════

def verify_signature(payload: bytes, signature: str) -> bool:
    """Meta webhook imzosini tekshirish"""
    if not META_APP_SECRET or not signature:
        return True  # Development mode
    expected = "sha256=" + hmac.new(
        META_APP_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


@app.get("/webhook")
async def webhook_verify(request: Request):
    """Meta webhook verification (GET)"""
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    print(f"🔔 Webhook verify: mode={mode}, token={token}")

    if mode == "subscribe" and token == WEBHOOK_VERIFY_TOKEN:
        print("✅ Webhook muvaffaqiyatli tasdiqlandi!")
        return PlainTextResponse(challenge)
    else:
        print(f"❌ Webhook tasdiqlash xatosi. Token: {token}")
        raise HTTPException(status_code=403, detail="Verify token noto'g'ri")


@app.post("/webhook")
async def webhook_receive(request: Request):
    """Instagram webhook eventlarini qabul qilish (POST)"""
    # Signature tekshirish
    body = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")

    if META_APP_SECRET and not verify_signature(body, signature):
        raise HTTPException(status_code=403, detail="Noto'g'ri imzo")

    try:
        data = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="JSON parse xatosi")

    print(f"📨 Webhook keldi: {json.dumps(data, indent=2)[:500]}")

    # Async ishlov berish
    asyncio.create_task(process_webhook(data))
    return {"status": "ok"}


async def process_webhook(data: dict):
    """Webhook datani asosiy ishlov berish"""
    try:
        object_type = data.get("object")

        # Instagram yoki Page events
        if object_type not in ("instagram", "page"):
            return

        accounts = await get_accounts()
        if not accounts:
            print("⚠️ Hech qanday akkaunt yo'q")
            return

        for entry in data.get("entry", []):
            # ── COMMENT eventlar ──
            changes = entry.get("changes", [])
            for change in changes:
                if change.get("field") == "comments":
                    await handle_comment_event(change["value"], accounts)

            # ── MESSAGING eventlar (DM)  ──
            messaging = entry.get("messaging", [])
            for msg_event in messaging:
                await handle_message_event(msg_event, accounts)

    except Exception as e:
        print(f"❌ Webhook ishlov berish xatosi: {e}")
        import traceback
        traceback.print_exc()


async def handle_comment_event(value: dict, accounts: list):
    """Kommentariya eventini ishlov berish"""
    from_user = value.get("from", {})
    sender_id = from_user.get("id")
    sender_name = from_user.get("name", "")
    comment_text = value.get("text", "")
    media_id = value.get("media", {}).get("id", "")

    if not sender_id or not comment_text:
        return

    print(f"💬 Yangi kommentariya: '{comment_text}' from {sender_id}")

    # Qaysi akkauntga tegishli ekanligini aniqlash
    # Hamma aktiv akkauntlarni tekshirish
    for account in accounts:
        if not account.get("is_active"):
            continue

        trigger = await find_matching_trigger(account["id"], comment_text)
        if not trigger:
            continue

        print(f"✅ Trigger topildi: '{trigger['keyword']}' → DM yuborilmoqda...")

        # Subscriber saqlash
        sub_id = await upsert_subscriber(account["id"], sender_id, sender_name)

        # DM yuborish
        result = await send_dm(sender_id, trigger["reply_message"], account["page_access_token"])

        # Log saqlash
        status = "sent" if "message_id" in result or "recipient_id" in result else "failed"
        await log_message(
            account_id=account["id"],
            subscriber_id=sub_id,
            trigger_id=trigger["id"],
            post_id=media_id,
            comment_text=comment_text,
            sent_message=trigger["reply_message"],
            status=status
        )
        break  # Birinchi mos akkaunt topilsa to'xtatish


async def handle_message_event(event: dict, accounts: list):
    """DM eventini ishlov berish — DM trigger logikasi"""
    sender = event.get("sender", {})
    sender_id = sender.get("id")
    message = event.get("message", {})
    message_text = message.get("text", "")

    if not sender_id or not message_text:
        return

    print(f"📩 DM keldi: '{message_text}' from {sender_id}")

    # Barcha aktiv akkauntlarda DM triggerini qidirish
    for account in accounts:
        if not account.get("is_active"):
            continue

        trigger = await find_matching_trigger(account["id"], message_text)
        if not trigger:
            continue

        print(f"✅ DM trigger topildi: '{trigger['keyword']}' → javob yuborilmoqda...")

        # Subscriber saqlash/yangilash
        sub_id = await upsert_subscriber(account["id"], sender_id)

        # DM javob yuborish
        result = await send_dm(sender_id, trigger["reply_message"], account["page_access_token"])

        # Log saqlash
        status = "sent" if "message_id" in result or "recipient_id" in result else "failed"
        await log_message(
            account_id=account["id"],
            subscriber_id=sub_id,
            trigger_id=trigger["id"],
            post_id="dm",
            comment_text=message_text,
            sent_message=trigger["reply_message"],
            status=status
        )
        break


# ════════════════════════════════════════════════
#  HEALTH CHECK
# ════════════════════════════════════════════════

@app.get("/health")
async def health_check():
    return {
        "status": "online",
        "service": "Instagram Chatbot",
        "webhook_token": WEBHOOK_VERIFY_TOKEN[:4] + "****"
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run("main:app", host=host, port=port, reload=True)
