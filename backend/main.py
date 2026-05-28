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
    get_accounts, create_account, delete_account, update_account_session,
    get_triggers, create_trigger, update_trigger, delete_trigger, find_matching_trigger,
    get_posts, add_post, toggle_post_monitoring, update_post_media_id,
    get_subscribers,
    upsert_subscriber,
    log_message, get_messages_log,
)
from instagrapi_client import (
    login_new, complete_2fa, get_client, clear_client_cache,
    ig_send_dm, ig_get_user_medias, ig_get_comments, ig_get_recent_dms
)
from instagram_api import (
    send_dm, get_instagram_account_info,
    get_post_info, verify_access_token, subscribe_to_webhooks,
    get_user_media, get_media_comments, get_ig_conversations, get_page_id
)

import datetime

load_dotenv()

WEBHOOK_VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN", "my_secret_verify_token_123")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))  # soniya

# ── Polling state ──
_processed_comment_ids: set = set()
_processed_dm_ids: set = set()
_poll_stats = {
    "running": False,
    "last_poll": None,
    "polls_done": 0,
    "comments_found": 0,
    "dms_sent": 0,
    "errors": 0,
}
# In-memory debug log (oxirgi 200 ta yozuv)
_debug_log: list = []

def _log(msg: str):
    ts = datetime.datetime.utcnow().strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    print(entry)
    _debug_log.append(entry)
    if len(_debug_log) > 200:
        _debug_log.pop(0)

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
    asyncio.create_task(polling_loop())
    print(f"🔄 Polling rejimi yoqildi (har {POLL_INTERVAL}s)")


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
    page_access_token: Optional[str] = None


class AccountLoginIG(BaseModel):
    username: str
    password: str


class AccountLogin2FA(BaseModel):
    username: str
    code: str


@app.get("/api/accounts")
async def api_get_accounts(auth=Depends(check_admin)):
    rows = await get_accounts()
    # Parolni va session ni frontendga yubormaymiz
    for r in rows:
        r.pop("ig_session", None)
    return rows


@app.post("/api/accounts")
async def api_create_account(body: AccountCreate, auth=Depends(check_admin)):
    if not body.page_access_token:
        raise HTTPException(status_code=400, detail="Token kiriting yoki /api/accounts/ig-login ishlating")
    verify = await verify_access_token(body.page_access_token)
    if not verify.get("valid"):
        raise HTTPException(status_code=400, detail=f"Token noto'g'ri: {verify.get('error', '')}")
    ig_info = await get_instagram_account_info(body.page_access_token)
    if "error" in ig_info:
        raise HTTPException(status_code=400, detail=ig_info["error"])
    fb_page_id = await get_page_id(body.page_access_token)
    account = await create_account(
        instagram_id=ig_info.get("id"),
        username=ig_info.get("username", ig_info.get("name", "Unknown")),
        page_access_token=body.page_access_token,
        page_id=fb_page_id,
        auth_type="token"
    )
    return account


@app.post("/api/accounts/ig-login")
async def api_ig_login(body: AccountLoginIG, auth=Depends(check_admin)):
    """Instagram username + parol bilan akkaunt ulash"""
    print(f"🔐 Instagram login: @{body.username}")
    result = await login_new(body.username, body.password)

    if result.get("need_2fa"):
        # 2FA kerak — frontendga bildirамиз
        return JSONResponse(status_code=202, content={
            "need_2fa": True,
            "username": body.username,
            "message": "2FA kod kerak — authenticator ilovasidagi kodni kiriting",
        })

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Login xatosi"))

    account = await create_account(
        instagram_id=result["ig_user_id"],
        username=result["username"],
        ig_username=result["username"],
        ig_session=result["session"],
        auth_type="instagrapi"
    )
    print(f"✅ @{result['username']} ulandi (instagrapi)")
    account.pop("ig_session", None)
    return account


@app.post("/api/accounts/ig-2fa")
async def api_ig_2fa(body: AccountLogin2FA, auth=Depends(check_admin)):
    """2FA kodini tekshirib loginni yakunlash"""
    print(f"🔑 2FA verify: @{body.username} — kod: {body.code}")
    result = await complete_2fa(body.username, body.code)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "2FA xatosi"))

    account = await create_account(
        instagram_id=result["ig_user_id"],
        username=result["username"],
        ig_username=result["username"],
        ig_session=result["session"],
        auth_type="instagrapi"
    )
    print(f"✅ @{result['username']} 2FA bilan ulandi")
    account.pop("ig_session", None)
    return account


@app.delete("/api/accounts/{account_id}")
async def api_delete_account(account_id: int, auth=Depends(check_admin)):
    clear_client_cache(account_id)
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
    match_all: int = 0
    trigger_type: str = 'comment'


class TriggerUpdate(BaseModel):
    keyword: str
    reply_message: str
    is_active: int = 1
    match_all: int = 0
    trigger_type: str = 'comment'


@app.get("/api/triggers")
async def api_get_triggers(account_id: Optional[int] = None, auth=Depends(check_admin)):
    return await get_triggers(account_id)


@app.post("/api/triggers")
async def api_create_trigger(body: TriggerCreate, auth=Depends(check_admin)):
    trigger_id = await create_trigger(
        body.account_id, body.keyword, body.reply_message,
        body.match_all, body.trigger_type
    )
    return {"id": trigger_id, "success": True}


@app.put("/api/triggers/{trigger_id}")
async def api_update_trigger(trigger_id: int, body: TriggerUpdate, auth=Depends(check_admin)):
    await update_trigger(trigger_id, body.keyword, body.reply_message,
                         body.is_active, body.match_all, body.trigger_type)
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

    result = await _smart_send_dm(account, body.recipient_id, body.message)
    if "error" in result and not result.get("success"):
        raise HTTPException(status_code=400, detail=str(result.get("error", "Xato")))
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


# ════════════════════════════════════════════════
#  POLLING ENGINE
# ════════════════════════════════════════════════

_server_start = datetime.datetime.utcnow()


async def polling_loop():
    """Davriy polling asosiy loop"""
    global _poll_stats
    await asyncio.sleep(3)  # serverga ishga tushish uchun vaqt
    _poll_stats["running"] = True
    print("🔄 Polling loop boshlandi")

    while True:
        try:
            await poll_all_accounts()
            _poll_stats["polls_done"] += 1
            _poll_stats["last_poll"] = datetime.datetime.utcnow().isoformat()
        except Exception as e:
            _poll_stats["errors"] += 1
            print(f"❌ Polling loop xatosi: {e}")
        await asyncio.sleep(POLL_INTERVAL)


async def poll_all_accounts():
    """Barcha aktiv akkauntlarni tekshirish"""
    accounts = await get_accounts()
    if not accounts:
        return
    for account in accounts:
        if not account.get("is_active"):
            continue
        await poll_comments(account)
        await poll_dms(account)


async def poll_comments(account: dict):
    """Yangi kommentariyalarni tekshirish"""
    global _poll_stats
    auth_type = account.get("auth_type", "token")

    if auth_type == "instagrapi":
        await _poll_comments_instagrapi(account)
    else:
        await _poll_comments_token(account)


async def _poll_comments_instagrapi(account: dict):
    """instagrapi orqali kommentariyalarni tekshirish"""
    global _poll_stats
    uname = account.get("username", "?")
    try:
        medias = await ig_get_user_medias(account, amount=10)
        media_map = {m["shortcode"]: m["id"] for m in medias}
        for shortcode, num_id in media_map.items():
            await update_post_media_id(shortcode, num_id)
        _log(f"📷 @{uname}: {len(medias)} media topildi")
    except Exception as e:
        _log(f"❌ @{uname} media xatosi: {e}")
        _poll_stats["errors"] += 1
        return

    posts = await get_posts(account["id"])
    monitored = [p for p in posts if p.get("is_monitoring")]
    _log(f"👁 @{uname}: {len(monitored)} post monitoring da")
    for post in posts:
        if not post.get("is_monitoring"):
            continue
        media_id = post.get("media_numeric_id") or media_map.get(post["post_id"])
        if not media_id:
            _log(f"⚠️ @{uname}: post {post['post_id']} — media_id topilmadi (50 ta eng yangi postdan biri emas?)")
            continue
        try:
            comments = await ig_get_comments(account, str(media_id), amount=50)
            if comments:
                newest_ts = comments[0].get("timestamp", "?")
                _log(f"💬 @{uname} post {post['post_id']}: {len(comments)} kommentariya (eng yangi: {newest_ts})")
            else:
                _log(f"💬 @{uname} post {post['post_id']}: 0 kommentariya")
        except Exception as e:
            _log(f"❌ @{uname} comments xatosi: {e}")
            continue
        await _process_new_comments(comments, media_id, account)


async def _poll_comments_token(account: dict):
    """Graph API token orqali kommentariyalarni tekshirish"""
    global _poll_stats
    ig_user_id = account.get("instagram_id")
    token = account.get("page_access_token")
    if not ig_user_id or not token:
        return
    try:
        media_list = await get_user_media(ig_user_id, token)
        media_map = {m["shortcode"]: m["id"] for m in media_list}
        for shortcode, num_id in media_map.items():
            await update_post_media_id(shortcode, num_id)
    except Exception as e:
        print(f"❌ Token media xatosi: {e}")
        _poll_stats["errors"] += 1
        return
    posts = await get_posts(account["id"])
    for post in posts:
        if not post.get("is_monitoring"):
            continue
        media_id = post.get("media_numeric_id") or media_map.get(post["post_id"])
        if not media_id:
            continue
        try:
            comments = await get_media_comments(media_id, token, limit=20)
        except Exception as e:
            print(f"❌ Token comments xatosi: {e}")
            continue
        await _process_new_comments(comments, media_id, account)


async def _process_new_comments(comments: list, media_id: str, account: dict):
    """Yangi kommentariyalarni qayta ishlash (instagrapi va token uchun umumiy)"""
    global _poll_stats
    for comment in reversed(comments):
        cid = comment.get("id")
        if not cid or cid in _processed_comment_ids:
            continue
        _processed_comment_ids.add(cid)
        try:
            ctime_str = comment.get("timestamp", "")
            if ctime_str:
                ctime = datetime.datetime.fromisoformat(ctime_str.replace("Z", "+00:00"))
                ctime_utc = ctime.replace(tzinfo=None)
                # 2 daqiqa buferi — deploy vaqtidagi kommentariyalar ham o'tsin
                filter_time = _server_start - datetime.timedelta(minutes=2)
                if ctime_utc < filter_time:
                    _log(f"⏭ Eski kommentariya o'tkazildi: '{comment.get('text','')}' ({ctime_str})")
                    continue
        except Exception:
            pass
        _poll_stats["comments_found"] += 1
        _log(f"🆕 YANGI kommentariya: '{comment.get('text', '')}' — @{account.get('username')}")
        from_user = comment.get("from", {})
        value = {
            "from": from_user,
            "text": comment.get("text", ""),
            "media": {"id": str(media_id)}
        }
        asyncio.create_task(handle_comment_event(value, [account]))


async def poll_dms(account: dict):
    """Yangi DM larni tekshirish"""
    global _poll_stats
    auth_type = account.get("auth_type", "token")

    if auth_type == "instagrapi":
        await _poll_dms_instagrapi(account)
    else:
        await _poll_dms_token(account)


async def _poll_dms_instagrapi(account: dict):
    """instagrapi orqali DM larni tekshirish"""
    try:
        messages = await ig_get_recent_dms(account, amount=10)
    except Exception as e:
        print(f"❌ instagrapi DM polling: {e}")
        return

    ig_user_id = account.get("instagram_id", "")
    for msg in messages:
        mid = msg.get("id")
        if not mid or mid in _processed_dm_ids:
            continue
        _processed_dm_ids.add(mid)

        # Server ishga tushishidan eski
        try:
            mtime_str = msg.get("timestamp", "")
            if mtime_str:
                mtime = datetime.datetime.fromisoformat(mtime_str.replace("Z", "+00:00"))
                mtime_utc = mtime.replace(tzinfo=None)
                if mtime_utc < _server_start:
                    continue
        except Exception:
            pass

        sender_id = msg.get("sender_id", "")
        if not sender_id or sender_id == ig_user_id:
            continue  # o'z xabarlarimiz

        msg_text = msg.get("text", "")
        if not msg_text:
            continue

        print(f"📩 Yangi DM (instagrapi): '{msg_text}' from {sender_id}")
        event = {"sender": {"id": sender_id}, "message": {"text": msg_text}}
        asyncio.create_task(handle_message_event(event, [account]))


async def _poll_dms_token(account: dict):
    """Graph API token orqali DM larni tekshirish"""
    token = account.get("page_access_token")
    page_id = account.get("page_id")
    if not page_id:
        try:
            pid = await get_page_id(token)
            if pid:
                from database import get_db
                db = await get_db()
                try:
                    await db.execute("UPDATE accounts SET page_id = ? WHERE id = ?", (pid, account["id"]))
                    await db.commit()
                finally:
                    await db.close()
                page_id = pid
        except Exception:
            return
    if not page_id:
        return
    try:
        conversations = await get_ig_conversations(page_id, token)
    except Exception as e:
        print(f"❌ Token DM polling: {e}")
        return
    for conv in conversations:
        messages = conv.get("messages", {}).get("data", [])
        for msg in reversed(messages):
            mid = msg.get("id")
            if not mid or mid in _processed_dm_ids:
                continue
            _processed_dm_ids.add(mid)
            try:
                mtime_str = msg.get("created_time", "")
                if mtime_str:
                    mtime = datetime.datetime.fromisoformat(mtime_str.replace("Z", "+00:00"))
                    if mtime.replace(tzinfo=None) < _server_start:
                        continue
            except Exception:
                pass
            from_info = msg.get("from", {})
            sender_id = from_info.get("id")
            if not sender_id or sender_id == page_id:
                continue
            msg_text = msg.get("message", "")
            if not msg_text:
                continue
            print(f"📩 Yangi DM (token): '{msg_text}' from {sender_id}")
            event = {"sender": {"id": sender_id}, "message": {"text": msg_text}}
            asyncio.create_task(handle_message_event(event, [account]))


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


async def _smart_send_dm(account: dict, recipient_id: str, message: str) -> dict:
    """instagrapi yoki token orqali DM yuborish"""
    auth_type = account.get("auth_type", "token")
    if auth_type == "instagrapi":
        return await ig_send_dm(account, recipient_id, message)
    else:
        token = account.get("page_access_token", "")
        return await send_dm(recipient_id, message, token)


def apply_template(message: str, name: str = "", username: str = "") -> str:
    """Xabar shablonidagi o'zgaruvchilarni almashtirish"""
    return (message
            .replace("{ism}", name or "Do'stim")
            .replace("{username}", username or "")
            .replace("{name}", name or "Do'stim"))


async def handle_comment_event(value: dict, accounts: list):
    """Kommentariya eventini ishlov berish"""
    from_user = value.get("from", {})
    sender_id = from_user.get("id")
    sender_name = from_user.get("name", "")
    sender_username = from_user.get("username", "")
    comment_text = value.get("text", "")
    media_id = value.get("media", {}).get("id", "")

    if not sender_id or not comment_text:
        return

    _log(f"💬 Kommentariya: '{comment_text}' from {sender_id}")

    for account in accounts:
        if not account.get("is_active"):
            continue

        trigger = await find_matching_trigger(account["id"], comment_text, trigger_type='comment')
        if not trigger:
            _log(f"⚠️ @{account.get('username')}: trigger topilmadi ('{comment_text}')")
            continue

        _log(f"✅ Trigger topildi: '{trigger['keyword']}' → DM yuborilmoqda @{sender_id}...")

        # Subscriber saqlash
        sub_id = await upsert_subscriber(account["id"], sender_id, sender_name)

        # Shablon o'zgaruvchilarini qo'llash
        final_message = apply_template(trigger["reply_message"], sender_name, sender_username)

        # DM yuborish (instagrapi yoki token)
        result = await _smart_send_dm(account, sender_id, final_message)
        _log(f"📤 DM natija: {result}")

        status = "sent" if result.get("success") or "message_id" in result or "recipient_id" in result or "thread_id" in result else "failed"
        await log_message(
            account_id=account["id"],
            subscriber_id=sub_id,
            trigger_id=trigger["id"],
            post_id=media_id,
            comment_text=comment_text,
            sent_message=final_message,
            status=status
        )
        _poll_stats["dms_sent"] += 1
        break


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

        trigger = await find_matching_trigger(account["id"], message_text, trigger_type='dm')
        if not trigger:
            continue

        print(f"✅ DM trigger topildi: '{trigger['keyword']}' → javob yuborilmoqda...")

        # Subscriber saqlash/yangilash
        sub_id = await upsert_subscriber(account["id"], sender_id)

        # Shablon o'zgaruvchilarini qo'llash
        final_dm = apply_template(trigger["reply_message"])

        # DM javob yuborish
        result = await _smart_send_dm(account, sender_id, final_dm)

        status = "sent" if result.get("success") or "message_id" in result or "thread_id" in result else "failed"
        await log_message(
            account_id=account["id"],
            subscriber_id=sub_id,
            trigger_id=trigger["id"],
            post_id="dm",
            comment_text=message_text,
            sent_message=final_dm,
            status=status
        )
        _poll_stats["dms_sent"] += 1
        break


# ════════════════════════════════════════════════
#  POLLING STATUS API
# ════════════════════════════════════════════════

@app.get("/api/polling/status")
async def api_polling_status(auth=Depends(check_admin)):
    return {
        **_poll_stats,
        "poll_interval": POLL_INTERVAL,
        "processed_comments": len(_processed_comment_ids),
        "processed_dms": len(_processed_dm_ids),
        "server_start": _server_start.isoformat(),
    }


@app.post("/api/polling/trigger")
async def api_polling_trigger(auth=Depends(check_admin)):
    """Qo'lda polling ishga tushirish"""
    asyncio.create_task(poll_all_accounts())
    return {"success": True, "message": "Polling boshlandi"}


@app.get("/api/debug/logs")
async def api_debug_logs(auth=Depends(check_admin)):
    """Oxirgi polling loglari"""
    return {"logs": list(reversed(_debug_log[-50:]))}


@app.get("/api/debug/status")
async def api_debug_status(auth=Depends(check_admin)):
    """To'liq tashxis: akkaunt sessiya + postlar + triggerlar"""
    accounts = await get_accounts()
    result = []
    for acc in accounts:
        posts = await get_posts(acc["id"])
        triggers = await get_triggers(acc["id"])
        from instagrapi_client import _clients, INSTAGRAPI_AVAILABLE
        session_cached = acc["id"] in _clients
        result.append({
            "account": acc.get("username"),
            "auth_type": acc.get("auth_type"),
            "is_active": acc.get("is_active"),
            "instagrapi_available": INSTAGRAPI_AVAILABLE,
            "session_cached": session_cached,
            "has_session": bool(acc.get("ig_session")),
            "posts_total": len(posts),
            "posts_monitoring": sum(1 for p in posts if p.get("is_monitoring")),
            "posts": [{"id": p["post_id"], "monitoring": p.get("is_monitoring"), "media_id": p.get("media_numeric_id")} for p in posts],
            "triggers_total": len(triggers),
            "triggers_active": sum(1 for t in triggers if t.get("is_active")),
            "triggers": [{"keyword": t["keyword"], "match_all": t.get("match_all"), "type": t.get("trigger_type"), "active": t.get("is_active")} for t in triggers],
        })
    return {
        "server_start": _server_start.isoformat(),
        "polls_done": _poll_stats["polls_done"],
        "accounts": result,
    }


@app.put("/api/polling/interval")
async def api_set_poll_interval(seconds: int, auth=Depends(check_admin)):
    global POLL_INTERVAL
    if seconds < 15 or seconds > 3600:
        raise HTTPException(status_code=400, detail="Interval 15-3600 soniya oralig'ida bo'lishi kerak")
    POLL_INTERVAL = seconds
    return {"success": True, "poll_interval": POLL_INTERVAL}


# ════════════════════════════════════════════════
#  HEALTH CHECK
# ════════════════════════════════════════════════

@app.get("/health")
async def health_check():
    return {
        "status": "online",
        "service": "Instagram Chatbot",
        "webhook_token": WEBHOOK_VERIFY_TOKEN[:4] + "****",
        "polling": _poll_stats["running"],
        "poll_interval": POLL_INTERVAL,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run("main:app", host=host, port=port, reload=True)
