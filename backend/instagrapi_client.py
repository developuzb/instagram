"""
Instagram Chatbot — Instagrapi Client
Rasmiy Meta API o'rniga Instagram ichki API (instagrapi)
Token, Meta App, Developer account SHART EMAS
"""

import json
import asyncio
from concurrent.futures import ThreadPoolExecutor

try:
    from instagrapi import Client
    from instagrapi.exceptions import (
        BadPassword, TwoFactorRequired,
        ChallengeRequired, UserNotFound
    )
    INSTAGRAPI_AVAILABLE = True
except ImportError as _e:
    print(f"⚠️ instagrapi o'rnatilmagan: {_e}. IG-login ishlamaydi.")
    INSTAGRAPI_AVAILABLE = False
    Client = None
    BadPassword = TwoFactorRequired = ChallengeRequired = UserNotFound = Exception

# Sinxron funksiyalar uchun thread pool
_executor = ThreadPoolExecutor(max_workers=3)

# Active klientlar keshi: account_id → Client
_clients: dict = {}

# 2FA kutayotgan klientlar: username → {"client": cl, "two_factor_identifier": "..."}
_pending_2fa: dict = {}


async def _run(func, *args):
    """Sinxron funksiyani async context da ishlatish"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, func, *args)


def _make_client():
    """Yangi instagrapi Client yaratish"""
    if not INSTAGRAPI_AVAILABLE:
        raise RuntimeError("instagrapi o'rnatilmagan")
    cl = Client()
    cl.delay_range = [1, 3]
    return cl


async def login_new(username: str, password: str) -> dict:
    """
    Yangi Instagram akkauntga kirish.
    Returns:
      {"success": True, "ig_user_id": "...", "session": "..."}
      {"success": False, "need_2fa": True, "two_factor_identifier": "..."}
      {"success": False, "error": "..."}
    """
    if not INSTAGRAPI_AVAILABLE:
        return {"success": False, "error": "instagrapi server da o'rnatilmagan."}

    uname = username.strip()

    def _login():
        cl = _make_client()
        try:
            cl.login(uname, password)
            user_info = cl.account_info()
            session = json.dumps(cl.get_settings())
            return {
                "success": True,
                "ig_user_id": str(user_info.pk),
                "username": user_info.username,
                "full_name": user_info.full_name,
                "session": session,
                "client": cl,
            }
        except TwoFactorRequired:
            return {
                "success": False,
                "need_2fa": True,
                "username": uname,
                "client": cl,
            }
        except BadPassword:
            return {"success": False, "error": "Noto'g'ri parol"}
        except ChallengeRequired:
            return {"success": False, "error": "Instagram tekshiruv talab qildi. Ilovada tasdiqlang yoki keyinroq urinib ko'ring."}
        except UserNotFound:
            return {"success": False, "error": "Foydalanuvchi topilmadi"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    result = await _run(_login)

    # 2FA holatida: klient + parolni saqlaymiz (login() ni qayta chaqirish uchun)
    if result.get("need_2fa") and result.get("client"):
        _pending_2fa[uname] = {
            "client": result["client"],
            "username": uname,
            "password": password,          # login() qayta chaqirilganda kerak
        }

    result.pop("client", None)
    return result


async def complete_2fa(username: str, code: str) -> dict:
    """
    2FA kodini yuborib loginni yakunlash.
    username: login_new() ga yuborilgan username
    code: authenticator ilovasidagi 6 xonali kod
    """
    pending = _pending_2fa.get(username.strip())
    if not pending:
        return {"success": False, "error": "Login sessiyasi topilmadi. Qaytadan username+parol kiriting."}

    def _verify():
        cl = pending["client"]
        uname = pending["username"]
        pwd = pending["password"]
        try:
            # Instagrapi 2.x: login() ni verification_code bilan qayta chaqirish
            cl.login(uname, pwd, verification_code=code.strip())
            user_info = cl.account_info()
            session = json.dumps(cl.get_settings())
            return {
                "success": True,
                "ig_user_id": str(user_info.pk),
                "username": user_info.username,
                "full_name": user_info.full_name,
                "session": session,
                "client": cl,
            }
        except Exception as e:
            err = str(e).lower()
            if "invalid" in err or "wrong" in err or "incorrect" in err or "bad" in err:
                return {"success": False, "error": "Noto'g'ri 2FA kod. Authenticatordagi yangi kodni kiriting."}
            return {"success": False, "error": str(e)}

    result = await _run(_verify)

    if result.get("success"):
        _pending_2fa.pop(username.strip(), None)
        result.pop("client", None)

    return result


async def get_client(account: dict):
    """
    Mavjud akkaunt uchun klient olish (keshdan yoki sessiyadan)
    account: DB dagi accounts qatori (dict)
    """
    account_id = account["id"]

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
            # user_id bo'lsa sessiya yuklangan deb hisoblaymiz
            if not cl.user_id:
                print(f"⚠️ Sessiya yuklanmadi ({username}): user_id yo'q")
                return None
            print(f"✅ Sessiya tiklandi: @{username} (user_id={cl.user_id})")
            return cl
        except Exception as e:
            print(f"❌ Sessiya tiklanmadi ({username}): {e}")
            return None

    cl = await _run(_restore)
    if cl:
        _clients[account_id] = cl
    return cl


async def refresh_session(account: dict):
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
    """Instagram DM yuborish"""
    cl = await get_client(account)
    if not cl:
        return {"error": "Klient topilmadi — qayta login qiling"}

    def _send():
        try:
            result = cl.direct_send(text, user_ids=[int(recipient_ig_id)])
            rid = getattr(result, "id", None) or getattr(result, "thread_id", None) or str(result)
            return {"success": True, "thread_id": str(rid)}
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
                for msg in thread.messages[:3]:
                    if msg.item_type != "text":
                        continue
                    messages.append({
                        "id": str(msg.id),
                        "text": msg.text or "",
                        "sender_id": str(msg.user_id),
                        "timestamp": msg.timestamp.isoformat() if msg.timestamp else "",
                    })
            return messages
        except Exception as e:
            print(f"❌ ig_get_recent_dms: {e}")
            return []

    return await _run(_get)
