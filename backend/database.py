"""
Database layer — PostgreSQL (asyncpg) yoki SQLite (aiosqlite) qo'llab-quvvatlaydi.
DATABASE_URL env var bo'lsa PostgreSQL, yo'qsa SQLite ishlatiladi.
"""
import os
import asyncio
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "")

# ──────────────────────────────────────────────
#  POSTGRESQL (asyncpg) rejimi
# ──────────────────────────────────────────────

_pg_pool = None

async def _get_pg_pool():
    global _pg_pool
    if _pg_pool is None:
        import asyncpg
        import ssl as _ssl
        # Supabase va boshqa cloud PG SSL talab qiladi
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        _pg_pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=1, max_size=5, ssl=ctx
        )
    return _pg_pool


async def _pg_init():
    pool = await _get_pg_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id SERIAL PRIMARY KEY,
                instagram_id TEXT UNIQUE,
                page_id TEXT,
                username TEXT,
                page_access_token TEXT,
                ig_username TEXT,
                ig_session TEXT,
                auth_type TEXT DEFAULT 'token',
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (NOW()::TEXT)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS triggers (
                id SERIAL PRIMARY KEY,
                account_id INTEGER,
                keyword TEXT NOT NULL,
                reply_message TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                match_all INTEGER DEFAULT 0,
                trigger_type TEXT DEFAULT 'comment',
                trigger_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (NOW()::TEXT)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id SERIAL PRIMARY KEY,
                account_id INTEGER,
                post_id TEXT UNIQUE NOT NULL,
                media_numeric_id TEXT,
                post_url TEXT,
                caption TEXT,
                is_monitoring INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (NOW()::TEXT)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                id SERIAL PRIMARY KEY,
                account_id INTEGER,
                instagram_user_id TEXT,
                username TEXT,
                first_interaction TEXT DEFAULT (NOW()::TEXT),
                last_interaction TEXT DEFAULT (NOW()::TEXT),
                message_count INTEGER DEFAULT 0,
                UNIQUE(account_id, instagram_user_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS messages_log (
                id SERIAL PRIMARY KEY,
                account_id INTEGER,
                subscriber_id INTEGER,
                trigger_id INTEGER,
                post_id TEXT,
                comment_text TEXT,
                sent_message TEXT,
                status TEXT DEFAULT 'sent',
                created_at TEXT DEFAULT (NOW()::TEXT)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        for key, val in [
            ('welcome_message', 'Salom! Sizning kommentariyangizni oldik.'),
            ('default_reply', 'Rahmat! Batafsil malumot uchun profilimizga qarang.'),
            ('auto_subscribe', '1'),
        ]:
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING",
                key, val
            )
    print("✅ PostgreSQL database initialized")


# ──────────────────────────────────────────────
#  SQLITE (aiosqlite) rejimi
# ──────────────────────────────────────────────

import aiosqlite

DB_PATH = "chatbot.db"

CREATE_TABLES_SQLITE = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instagram_id TEXT UNIQUE,
    page_id TEXT,
    username TEXT,
    page_access_token TEXT,
    ig_username TEXT,
    ig_session TEXT,
    auth_type TEXT DEFAULT 'token',
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS triggers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER,
    keyword TEXT NOT NULL,
    reply_message TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    match_all INTEGER DEFAULT 0,
    trigger_type TEXT DEFAULT 'comment',
    trigger_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER,
    post_id TEXT UNIQUE NOT NULL,
    media_numeric_id TEXT,
    post_url TEXT,
    caption TEXT,
    is_monitoring INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
CREATE TABLE IF NOT EXISTS subscribers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER,
    instagram_user_id TEXT,
    username TEXT,
    first_interaction TEXT DEFAULT (datetime('now')),
    last_interaction TEXT DEFAULT (datetime('now')),
    message_count INTEGER DEFAULT 0,
    UNIQUE(account_id, instagram_user_id),
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
CREATE TABLE IF NOT EXISTS messages_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER,
    subscriber_id INTEGER,
    trigger_id INTEGER,
    post_id TEXT,
    comment_text TEXT,
    sent_message TEXT,
    status TEXT DEFAULT 'sent',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

async def _sqlite_init():
    async with aiosqlite.connect(DB_PATH) as db:
        for stmt in CREATE_TABLES_SQLITE.strip().split(";"):
            s = stmt.strip()
            if s:
                await db.execute(s)
        for key, val in [
            ('welcome_message', 'Salom! Sizning kommentariyangizni oldik.'),
            ('default_reply', 'Rahmat! Batafsil malumot uchun profilimizga qarang.'),
            ('auto_subscribe', '1'),
        ]:
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val)
            )
        await db.commit()
    print("✅ SQLite database initialized")


async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


# ──────────────────────────────────────────────
#  UMUMIY init_db
# ──────────────────────────────────────────────

async def init_db():
    if DATABASE_URL:
        try:
            await _pg_init()
        except Exception as e:
            print(f"⚠️ PostgreSQL ulanmadi ({e}), SQLite ga o'tilmoqda")
            global DATABASE_URL
            DATABASE_URL = ""
            await _sqlite_init()
    else:
        await _sqlite_init()


# ──────────────────────────────────────────────
#  HELPER: ikki rejimda ishlash uchun
# ──────────────────────────────────────────────

def _row_to_dict(row):
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    try:
        return dict(row)
    except Exception:
        return dict(zip(row.keys(), row.values()))


# ──────────────────────────────────────────────
#  ACCOUNTS
# ──────────────────────────────────────────────

async def get_accounts():
    if DATABASE_URL:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM accounts ORDER BY created_at DESC")
            return [dict(r) for r in rows]
    else:
        db = await get_db()
        try:
            cursor = await db.execute("SELECT * FROM accounts ORDER BY created_at DESC")
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await db.close()


async def create_account(instagram_id: str, username: str, page_access_token: str = None,
                         page_id: str = None, ig_username: str = None,
                         ig_session: str = None, auth_type: str = "token"):
    if DATABASE_URL:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO accounts (instagram_id, page_id, username, page_access_token, ig_username, ig_session, auth_type)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT (instagram_id) DO UPDATE SET
                    username=EXCLUDED.username, page_access_token=EXCLUDED.page_access_token,
                    ig_username=EXCLUDED.ig_username, ig_session=EXCLUDED.ig_session,
                    auth_type=EXCLUDED.auth_type, page_id=EXCLUDED.page_id
            """, instagram_id, page_id, username, page_access_token, ig_username, ig_session, auth_type)
            row = await conn.fetchrow("SELECT * FROM accounts WHERE instagram_id = $1", instagram_id)
            return dict(row)
    else:
        db = await get_db()
        try:
            await db.execute(
                """INSERT OR REPLACE INTO accounts
                   (instagram_id, page_id, username, page_access_token, ig_username, ig_session, auth_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (instagram_id, page_id, username, page_access_token, ig_username, ig_session, auth_type)
            )
            await db.commit()
            cursor = await db.execute("SELECT * FROM accounts WHERE instagram_id = ?", (instagram_id,))
            row = await cursor.fetchone()
            return dict(row)
        finally:
            await db.close()


async def update_account_session(account_id: int, ig_session: str):
    if DATABASE_URL:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE accounts SET ig_session=$1 WHERE id=$2", ig_session, account_id)
    else:
        db = await get_db()
        try:
            await db.execute("UPDATE accounts SET ig_session=? WHERE id=?", (ig_session, account_id))
            await db.commit()
        finally:
            await db.close()


async def delete_account(account_id: int):
    if DATABASE_URL:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM accounts WHERE id=$1", account_id)
    else:
        db = await get_db()
        try:
            await db.execute("DELETE FROM accounts WHERE id=?", (account_id,))
            await db.commit()
        finally:
            await db.close()


# ──────────────────────────────────────────────
#  TRIGGERS
# ──────────────────────────────────────────────

async def get_triggers(account_id: int = None):
    if DATABASE_URL:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            if account_id:
                rows = await conn.fetch(
                    "SELECT * FROM triggers WHERE account_id=$1 ORDER BY created_at DESC", account_id)
            else:
                rows = await conn.fetch("SELECT * FROM triggers ORDER BY created_at DESC")
            return [dict(r) for r in rows]
    else:
        db = await get_db()
        try:
            if account_id:
                cursor = await db.execute(
                    "SELECT * FROM triggers WHERE account_id=? ORDER BY created_at DESC", (account_id,))
            else:
                cursor = await db.execute("SELECT * FROM triggers ORDER BY created_at DESC")
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await db.close()


async def create_trigger(account_id: int, keyword: str, reply_message: str,
                         match_all: int = 0, trigger_type: str = 'comment'):
    if DATABASE_URL:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            row_id = await conn.fetchval(
                "INSERT INTO triggers (account_id,keyword,reply_message,match_all,trigger_type) VALUES ($1,$2,$3,$4,$5) RETURNING id",
                account_id, keyword.strip().lower(), reply_message, match_all, trigger_type)
            return row_id
    else:
        db = await get_db()
        try:
            cursor = await db.execute(
                "INSERT INTO triggers (account_id,keyword,reply_message,match_all,trigger_type) VALUES (?,?,?,?,?)",
                (account_id, keyword.strip().lower(), reply_message, match_all, trigger_type))
            await db.commit()
            return cursor.lastrowid
        finally:
            await db.close()


async def update_trigger(trigger_id: int, keyword: str, reply_message: str,
                         is_active: int, match_all: int = 0, trigger_type: str = 'comment'):
    if DATABASE_URL:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE triggers SET keyword=$1,reply_message=$2,is_active=$3,match_all=$4,trigger_type=$5 WHERE id=$6",
                keyword.strip().lower(), reply_message, is_active, match_all, trigger_type, trigger_id)
    else:
        db = await get_db()
        try:
            await db.execute(
                "UPDATE triggers SET keyword=?,reply_message=?,is_active=?,match_all=?,trigger_type=? WHERE id=?",
                (keyword.strip().lower(), reply_message, is_active, match_all, trigger_type, trigger_id))
            await db.commit()
        finally:
            await db.close()


async def delete_trigger(trigger_id: int):
    if DATABASE_URL:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM triggers WHERE id=$1", trigger_id)
    else:
        db = await get_db()
        try:
            await db.execute("DELETE FROM triggers WHERE id=?", (trigger_id,))
            await db.commit()
        finally:
            await db.close()


async def find_matching_trigger(account_id: int, comment_text: str, trigger_type: str = 'comment'):
    comment_lower = comment_text.strip().lower()
    if DATABASE_URL:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM triggers WHERE account_id=$1 AND is_active=1 AND trigger_type=$2",
                account_id, trigger_type)
            match_all_trigger = None
            for row in rows:
                trigger = dict(row)
                if trigger.get('match_all'):
                    match_all_trigger = trigger
                    continue
                kw = trigger['keyword']
                if kw == comment_lower or kw in comment_lower:
                    await conn.execute(
                        "UPDATE triggers SET trigger_count=trigger_count+1 WHERE id=$1", trigger['id'])
                    return trigger
            if match_all_trigger:
                await conn.execute(
                    "UPDATE triggers SET trigger_count=trigger_count+1 WHERE id=$1", match_all_trigger['id'])
                return match_all_trigger
            return None
    else:
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM triggers WHERE account_id=? AND is_active=1 AND trigger_type=?",
                (account_id, trigger_type))
            rows = await cursor.fetchall()
            match_all_trigger = None
            for row in rows:
                trigger = dict(row)
                if trigger.get('match_all'):
                    match_all_trigger = trigger
                    continue
                kw = trigger['keyword']
                if kw == comment_lower or kw in comment_lower:
                    await db.execute(
                        "UPDATE triggers SET trigger_count=trigger_count+1 WHERE id=?", (trigger['id'],))
                    await db.commit()
                    return trigger
            if match_all_trigger:
                await db.execute(
                    "UPDATE triggers SET trigger_count=trigger_count+1 WHERE id=?", (match_all_trigger['id'],))
                await db.commit()
                return match_all_trigger
            return None
        finally:
            await db.close()


# ──────────────────────────────────────────────
#  POSTS
# ──────────────────────────────────────────────

async def get_posts(account_id: int = None):
    if DATABASE_URL:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            if account_id:
                rows = await conn.fetch(
                    "SELECT * FROM posts WHERE account_id=$1 ORDER BY created_at DESC", account_id)
            else:
                rows = await conn.fetch("SELECT * FROM posts ORDER BY created_at DESC")
            return [dict(r) for r in rows]
    else:
        db = await get_db()
        try:
            if account_id:
                cursor = await db.execute(
                    "SELECT * FROM posts WHERE account_id=? ORDER BY created_at DESC", (account_id,))
            else:
                cursor = await db.execute("SELECT * FROM posts ORDER BY created_at DESC")
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await db.close()


async def add_post(account_id: int, post_id: str, post_url: str = "", caption: str = "", media_numeric_id: str = None):
    if DATABASE_URL:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO posts (account_id,post_id,media_numeric_id,post_url,caption) VALUES ($1,$2,$3,$4,$5) ON CONFLICT (post_id) DO NOTHING",
                account_id, post_id, media_numeric_id, post_url, caption)
    else:
        db = await get_db()
        try:
            await db.execute(
                "INSERT OR IGNORE INTO posts (account_id,post_id,media_numeric_id,post_url,caption) VALUES (?,?,?,?,?)",
                (account_id, post_id, media_numeric_id, post_url, caption))
            await db.commit()
        finally:
            await db.close()


async def update_post_media_id(post_shortcode: str, media_numeric_id: str):
    if DATABASE_URL:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE posts SET media_numeric_id=$1 WHERE post_id=$2 AND media_numeric_id IS NULL",
                media_numeric_id, post_shortcode)
    else:
        db = await get_db()
        try:
            await db.execute(
                "UPDATE posts SET media_numeric_id=? WHERE post_id=? AND media_numeric_id IS NULL",
                (media_numeric_id, post_shortcode))
            await db.commit()
        finally:
            await db.close()


async def toggle_post_monitoring(post_id: int, is_monitoring: int):
    if DATABASE_URL:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE posts SET is_monitoring=$1 WHERE id=$2", is_monitoring, post_id)
    else:
        db = await get_db()
        try:
            await db.execute("UPDATE posts SET is_monitoring=? WHERE id=?", (is_monitoring, post_id))
            await db.commit()
        finally:
            await db.close()


# ──────────────────────────────────────────────
#  SUBSCRIBERS
# ──────────────────────────────────────────────

async def get_subscribers(account_id: int = None):
    if DATABASE_URL:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            if account_id:
                rows = await conn.fetch(
                    "SELECT * FROM subscribers WHERE account_id=$1 ORDER BY last_interaction DESC", account_id)
            else:
                rows = await conn.fetch("SELECT * FROM subscribers ORDER BY last_interaction DESC")
            return [dict(r) for r in rows]
    else:
        db = await get_db()
        try:
            if account_id:
                cursor = await db.execute(
                    "SELECT * FROM subscribers WHERE account_id=? ORDER BY last_interaction DESC", (account_id,))
            else:
                cursor = await db.execute("SELECT * FROM subscribers ORDER BY last_interaction DESC")
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await db.close()


async def upsert_subscriber(account_id: int, instagram_user_id: str, username: str = ""):
    now = datetime.utcnow().isoformat()
    if DATABASE_URL:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO subscribers (account_id,instagram_user_id,username,first_interaction,last_interaction,message_count)
                VALUES ($1,$2,$3,$4,$5,1)
                ON CONFLICT (account_id,instagram_user_id) DO UPDATE SET
                    last_interaction=$4, message_count=subscribers.message_count+1,
                    username=CASE WHEN $3!='' THEN $3 ELSE subscribers.username END
            """, account_id, instagram_user_id, username, now, now)
            row = await conn.fetchrow(
                "SELECT id FROM subscribers WHERE account_id=$1 AND instagram_user_id=$2",
                account_id, instagram_user_id)
            return row['id'] if row else None
    else:
        db = await get_db()
        try:
            await db.execute("""
                INSERT INTO subscribers (account_id,instagram_user_id,username,first_interaction,last_interaction,message_count)
                VALUES (?,?,?,?,?,1)
                ON CONFLICT(account_id,instagram_user_id) DO UPDATE SET
                    last_interaction=?, message_count=message_count+1,
                    username=CASE WHEN ?!='' THEN ? ELSE username END
            """, (account_id, instagram_user_id, username, now, now, now, username, username))
            await db.commit()
            cursor = await db.execute(
                "SELECT id FROM subscribers WHERE account_id=? AND instagram_user_id=?",
                (account_id, instagram_user_id))
            row = await cursor.fetchone()
            return row[0] if row else None
        finally:
            await db.close()


# ──────────────────────────────────────────────
#  MESSAGES LOG
# ──────────────────────────────────────────────

async def log_message(account_id, subscriber_id, trigger_id, post_id, comment_text, sent_message, status="sent"):
    if DATABASE_URL:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO messages_log (account_id,subscriber_id,trigger_id,post_id,comment_text,sent_message,status)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
            """, account_id, subscriber_id, trigger_id, post_id, comment_text, sent_message, status)
    else:
        db = await get_db()
        try:
            await db.execute("""
                INSERT INTO messages_log (account_id,subscriber_id,trigger_id,post_id,comment_text,sent_message,status)
                VALUES (?,?,?,?,?,?,?)
            """, (account_id, subscriber_id, trigger_id, post_id, comment_text, sent_message, status))
            await db.commit()
        finally:
            await db.close()


async def get_messages_log(account_id: int = None, limit: int = 100):
    if DATABASE_URL:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            if account_id:
                rows = await conn.fetch("""
                    SELECT ml.*, s.username
                    FROM messages_log ml
                    LEFT JOIN subscribers s ON ml.subscriber_id=s.id
                    WHERE ml.account_id=$1
                    ORDER BY ml.created_at DESC LIMIT $2
                """, account_id, limit)
            else:
                rows = await conn.fetch("""
                    SELECT ml.*, s.username
                    FROM messages_log ml
                    LEFT JOIN subscribers s ON ml.subscriber_id=s.id
                    ORDER BY ml.created_at DESC LIMIT $1
                """, limit)
            return [dict(r) for r in rows]
    else:
        db = await get_db()
        try:
            if account_id:
                cursor = await db.execute("""
                    SELECT ml.*, s.username FROM messages_log ml
                    LEFT JOIN subscribers s ON ml.subscriber_id=s.id
                    WHERE ml.account_id=? ORDER BY ml.created_at DESC LIMIT ?
                """, (account_id, limit))
            else:
                cursor = await db.execute("""
                    SELECT ml.*, s.username FROM messages_log ml
                    LEFT JOIN subscribers s ON ml.subscriber_id=s.id
                    ORDER BY ml.created_at DESC LIMIT ?
                """, (limit,))
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await db.close()


# ──────────────────────────────────────────────
#  STATS
# ──────────────────────────────────────────────

async def get_stats():
    if DATABASE_URL:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            stats = {}
            for table, label in [
                ("accounts", "total_accounts"), ("triggers", "total_triggers"),
                ("subscribers", "total_subscribers"), ("messages_log", "total_messages"),
                ("posts", "total_posts"),
            ]:
                val = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                stats[label] = val
            today = await conn.fetchval(
                "SELECT COUNT(*) FROM messages_log WHERE created_at::date = CURRENT_DATE")
            stats["today_messages"] = today
            return stats
    else:
        db = await get_db()
        try:
            stats = {}
            for table, label in [
                ("accounts", "total_accounts"), ("triggers", "total_triggers"),
                ("subscribers", "total_subscribers"), ("messages_log", "total_messages"),
                ("posts", "total_posts"),
            ]:
                cursor = await db.execute(f"SELECT COUNT(*) FROM {table}")
                row = await cursor.fetchone()
                stats[label] = row[0]
            cursor = await db.execute(
                "SELECT COUNT(*) FROM messages_log WHERE date(created_at)=date('now')")
            row = await cursor.fetchone()
            stats["today_messages"] = row[0]
            return stats
        finally:
            await db.close()
