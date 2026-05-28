"""
Instagram Chatbot — Instagrapi Client
Rasmiy Meta API o'rniga Instagram ichki API (instagrapi)
Token, Meta App, Developer account SHART EMAS
"""

import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired, BadPassword, TwoFactorRequired,
    ChallengeRequired, UserNotFound, ClientError
)

# Sinxron funksiyalar uchun thread pool
_executor = ThreadPoolExecutor(max_workers=3)

# Active klientlar keshi: account_id → Client
_clients: dict = {}


async def _run(func, *args):
    """Sinxron funksiyani async context da ishlatish"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, func, *args)


def _make_client() -> Client:
    """Yangi instagrapi Client yaratish"""
    cl = Client()
    cl.delay_range = [1, 3]  # so'rovlar orasida 1-3 soniya kutish
    return cl


async def login_new(username: str, password: str) -> dict:
    """
    Yangi Instagram akkauntga kirish.
    Returns: {"success": True, "ig_user_id": "...", "session": "...json..."}
             {"success": False, "error": "...", "need_2fa": True/False}
    """
    def _login():
        cl = _make_client()
        try:
            cl.login(username.strip(), password)
            user_info = cl.account_info()
            session = json.dumps(cl.get_settings())
            return {
                "success": True,
                "ig_user_id": str(user_info.pk),
                "username": user_info.username,
                "full_name": user_info.full_name,
                "session": session,
                "client": cl
            }
        except BadPassword:
            return {"success": False, "error": "Noto'g'ri parol"}
        except TwoFactorRequired:
            return {"success": False, "error": "2FA yoqilgan — kod kiriting", "need_2fa": True}
        except ChallengeRequired:
            return {"success": False, "error": "Instagram challenge talab qildi. Keyinroq urinib ko'ring yoki ilovada tasdiqlang."}
        except UserNotFound:
            return {"success": False, "error": "Foydalanuvchi topilmadi"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    result = await _run(_login)
    if result.get("success") and result.get("client"):
        # klientni keshlamiz — session yangilanadi
        # account_id keyinroq bilib olinadi, username bilan saqlaymiz
        pass
    return result


async def get_client(account: dict) -> Client | None:
    """
    Mavjud akkaunt uchun klient olish (keshdan yoki sessiyadan)
    account: DB dagi accounts qatori (dict)
    """
    account_id = account["id"]

    # Keshda bor?
    if account_id in _clients:
        return _clients[account_id]

    session_json = account.get("ig_session")
    username = account.get("ig_username")
    if not session_json or not username:
        return None

    def _restore():
        try:
            cl = _make_client()
            settings = json.loads(session_json)
            cl.set_settings(settings)
            cl.login(username, "")  # sessiya bilan tiklash
            return cl
        except Exception as e:
            print(f"❌ Sessiya tiklanmadi ({username}): {e}")
            return None

    cl = await _run(_restore)
    if cl:
        _clients[account_id] = cl
    return cl


async def refresh_session(account: dict) -> str | None:
    """Sessiyani yangilab, JSON string qaytarish"""
    cl = await get_client(account)
    if not cl:
        return None
    try:
        settings = await _run(cl.get_settings)
        return json.dumps(settings)
    except Exception:
        return None


def clear_client_cache(account_id: int):
    """Klientni keshdan o'chirish (logout, o'chirish paytida)"""
    _clients.pop(account_id, None)


# ══════════════════════════════════
#  ASOSIY FUNKSIYALAR
# ══════════════════════════════════

async def ig_send_dm(account: dict, recipient_ig_id: str, text: str) -> dict:
    """
    Instagram DM yuborish (instagrapi orqali)
    recipient_ig_id: string raqam (Instagram user ID)
    """
    cl = await get_client(account)
    if not cl:
        return {"error": "Klient topilmadi — qayta login qiling"}

    def _send():
        try:
            thread = cl.direct_send(text, user_ids=[int(recipient_ig_id)])
            return {"success": True, "thread_id": str(thread.id)}
        except Exception as e:
            return {"error": str(e)}

    return await _run(_send)


async def ig_get_user_medias(account: dict, amount: int = 12) -> list:
    """Akkauntning so'nggi postlari"""
    cl = await get_client(account)
    if not cl:
        return []

    def _get():
        try:
            user_id = int(account["instagram_id"])
            medias = cl.user_medias(user_id, amount)
            return [
                {
                    "id": str(m.id),
                    "shortcode": m.code,
                    "timestamp": m.taken_at.isoformat() if m.taken_at else "",
                    "media_type": m.media_type,
                    "permalink": f"https://instagram.com/p/{m.code}/"
                }
                for m in medias
            ]
        except Exception as e:
            print(f"❌ ig_get_user_medias: {e}")
            return []

    return await _run(_get)


async def ig_get_comments(account: dict, media_id: str, amount: int = 20) -> list:
    """Post kommentariyalarini olish"""
    cl = await get_client(account)
    if not cl:
        return []

    def _get():
        try:
            comments = cl.media_comments(int(media_id), amount)
            return [
                {
                    "id": str(c.pk),
                    "text": c.text,
                    "timestamp": c.created_at_utc.isoformat() if c.created_at_utc else "",
                    "from": {
                        "id": str(c.user.pk),
                        "username": c.user.username,
                        "name": c.user.full_name or c.user.username
                    }
                }
                for c in comments
            ]
        except Exception as e:
            print(f"❌ ig_get_comments ({media_id}): {e}")
            return []

    return await _run(_get)


async def ig_get_recent_dms(account: dict, amount: int = 10) -> list:
    """So'nggi DM suhbatlarini olish"""
    cl = await get_client(account)
    if not cl:
        return []

    def _get():
        try:
            threads = cl.direct_threads(amount=amount)
            messages = []
            for thread in threads:
                if not thread.messages:
                    continue
                for msg in thread.messages[:3]:  # har threaddan oxirgi 3 xabar
                    if msg.item_type != "text":
                        continue
                    sender_id = str(msg.user_id)
                    messages.append({
                        "id": str(msg.id),
                        "text": msg.text or "",
                        "sender_id": sender_id,
                        "timestamp": msg.timestamp.isoformat() if msg.timestamp else "",
                    })
            return messages
        except Exception as e:
            print(f"❌ ig_get_recent_dms: {e}")
            return []

    return await _run(_get)


async def ig_get_account_info(username: str, session_json: str) -> dict:
    """Sessiya orqali akkaunt ma'lumotlarini olish"""
    def _get():
        try:
            cl = _make_client()
            cl.set_settings(json.loads(session_json))
            info = cl.account_info()
            return {
                "id": str(info.pk),
                "username": info.username,
                "full_name": info.full_name,
                "followers_count": info.follower_count,
            }
        except Exception as e:
            return {"error": str(e)}

    return await _run(_get)
