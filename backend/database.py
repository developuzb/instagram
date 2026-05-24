import aiosqlite
import asyncio
from datetime import datetime

DB_PATH = "chatbot.db"

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instagram_id TEXT UNIQUE,
    page_id TEXT,
    username TEXT,
    page_access_token TEXT,
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

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        for statement in CREATE_TABLES.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                await db.execute(stmt)

        # Default settings — parameterized so'rovlar (apostrof xatosidan himoya)
        defaults = [
            ('welcome_message', 'Salom! Sizning kommentariyangizni oldik. Tez orada javob beramiz!'),
            ('default_reply', 'Rahmat! Batafsil malumot uchun profilimizga qarang.'),
            ('auto_subscribe', '1'),
        ]
        for key, val in defaults:
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, val)
            )
        await db.commit()
    print("✅ Database initialized successfully")


async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


# ──────────────────────── ACCOUNTS ────────────────────────

async def get_accounts():
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM accounts ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def create_account(instagram_id: str, username: str, page_access_token: str, page_id: str = None):
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO accounts (instagram_id, page_id, username, page_access_token) VALUES (?, ?, ?, ?)",
            (instagram_id, page_id, username, page_access_token)
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM accounts WHERE instagram_id = ?", (instagram_id,))
        row = await cursor.fetchone()
        return dict(row)
    finally:
        await db.close()


async def delete_account(account_id: int):
    db = await get_db()
    try:
        await db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        await db.commit()
    finally:
        await db.close()


# ──────────────────────── TRIGGERS ────────────────────────

async def get_triggers(account_id: int = None):
    db = await get_db()
    try:
        if account_id:
            cursor = await db.execute(
                "SELECT * FROM triggers WHERE account_id = ? ORDER BY created_at DESC", (account_id,)
            )
        else:
            cursor = await db.execute("SELECT * FROM triggers ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def create_trigger(account_id: int, keyword: str, reply_message: str,
                         match_all: int = 0, trigger_type: str = 'comment'):
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO triggers (account_id, keyword, reply_message, match_all, trigger_type) VALUES (?, ?, ?, ?, ?)",
            (account_id, keyword.strip().lower(), reply_message, match_all, trigger_type)
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def update_trigger(trigger_id: int, keyword: str, reply_message: str,
                         is_active: int, match_all: int = 0, trigger_type: str = 'comment'):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE triggers SET keyword=?, reply_message=?, is_active=?, match_all=?, trigger_type=? WHERE id=?",
            (keyword.strip().lower(), reply_message, is_active, match_all, trigger_type, trigger_id)
        )
        await db.commit()
    finally:
        await db.close()


async def delete_trigger(trigger_id: int):
    db = await get_db()
    try:
        await db.execute("DELETE FROM triggers WHERE id = ?", (trigger_id,))
        await db.commit()
    finally:
        await db.close()


async def find_matching_trigger(account_id: int, comment_text: str, trigger_type: str = 'comment'):
    db = await get_db()
    try:
        comment_lower = comment_text.strip().lower()
        cursor = await db.execute(
            "SELECT * FROM triggers WHERE account_id = ? AND is_active = 1 AND trigger_type = ?",
            (account_id, trigger_type)
        )
        rows = await cursor.fetchall()
        match_all_trigger = None
        for row in rows:
            trigger = dict(row)
            kw = trigger['keyword']
            # match_all trigger — barcha kommentariyalarga javob
            if trigger.get('match_all'):
                match_all_trigger = trigger
                continue
            # Exact match yoki comment ichida kalit so'z bor
            if kw == comment_lower or kw in comment_lower:
                await db.execute(
                    "UPDATE triggers SET trigger_count = trigger_count + 1 WHERE id = ?",
                    (trigger['id'],)
                )
                await db.commit()
                return trigger
        # Kalit so'z topilmasa — match_all trigger ishlatiladi
        if match_all_trigger:
            await db.execute(
                "UPDATE triggers SET trigger_count = trigger_count + 1 WHERE id = ?",
                (match_all_trigger['id'],)
            )
            await db.commit()
            return match_all_trigger
        return None
    finally:
        await db.close()


# ──────────────────────── POSTS ────────────────────────

async def get_posts(account_id: int = None):
    db = await get_db()
    try:
        if account_id:
            cursor = await db.execute(
                "SELECT * FROM posts WHERE account_id = ? ORDER BY created_at DESC", (account_id,)
            )
        else:
            cursor = await db.execute("SELECT * FROM posts ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def add_post(account_id: int, post_id: str, post_url: str = "", caption: str = "", media_numeric_id: str = None):
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR IGNORE INTO posts (account_id, post_id, media_numeric_id, post_url, caption) VALUES (?, ?, ?, ?, ?)",
            (account_id, post_id, media_numeric_id, post_url, caption)
        )
        await db.commit()
    finally:
        await db.close()


async def update_post_media_id(post_shortcode: str, media_numeric_id: str):
    """Post shortcode bo'yicha numeric media ID ni yangilash"""
    db = await get_db()
    try:
        await db.execute(
            "UPDATE posts SET media_numeric_id = ? WHERE post_id = ? AND media_numeric_id IS NULL",
            (media_numeric_id, post_shortcode)
        )
        await db.commit()
    finally:
        await db.close()


async def toggle_post_monitoring(post_id: int, is_monitoring: int):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE posts SET is_monitoring = ? WHERE id = ?",
            (is_monitoring, post_id)
        )
        await db.commit()
    finally:
        await db.close()


# ──────────────────────── SUBSCRIBERS ────────────────────────

async def get_subscribers(account_id: int = None):
    db = await get_db()
    try:
        if account_id:
            cursor = await db.execute(
                "SELECT * FROM subscribers WHERE account_id = ? ORDER BY last_interaction DESC",
                (account_id,)
            )
        else:
            cursor = await db.execute("SELECT * FROM subscribers ORDER BY last_interaction DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def upsert_subscriber(account_id: int, instagram_user_id: str, username: str = ""):
    db = await get_db()
    try:
        now = datetime.utcnow().isoformat()
        await db.execute("""
            INSERT INTO subscribers (account_id, instagram_user_id, username, first_interaction, last_interaction, message_count)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(account_id, instagram_user_id)
            DO UPDATE SET
                last_interaction = ?,
                message_count = message_count + 1,
                username = CASE WHEN ? != '' THEN ? ELSE username END
        """, (account_id, instagram_user_id, username, now, now, now, username, username))
        await db.commit()
        cursor = await db.execute(
            "SELECT id FROM subscribers WHERE account_id = ? AND instagram_user_id = ?",
            (account_id, instagram_user_id)
        )
        row = await cursor.fetchone()
        return row[0] if row else None
    finally:
        await db.close()


# ──────────────────────── MESSAGES LOG ────────────────────────

async def log_message(account_id, subscriber_id, trigger_id, post_id, comment_text, sent_message, status="sent"):
    db = await get_db()
    try:
        await db.execute("""
            INSERT INTO messages_log
            (account_id, subscriber_id, trigger_id, post_id, comment_text, sent_message, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (account_id, subscriber_id, trigger_id, post_id, comment_text, sent_message, status))
        await db.commit()
    finally:
        await db.close()


async def get_messages_log(account_id: int = None, limit: int = 100):
    db = await get_db()
    try:
        if account_id:
            cursor = await db.execute("""
                SELECT ml.*, s.username
                FROM messages_log ml
                LEFT JOIN subscribers s ON ml.subscriber_id = s.id
                WHERE ml.account_id = ?
                ORDER BY ml.created_at DESC LIMIT ?
            """, (account_id, limit))
        else:
            cursor = await db.execute("""
                SELECT ml.*, s.username
                FROM messages_log ml
                LEFT JOIN subscribers s ON ml.subscriber_id = s.id
                ORDER BY ml.created_at DESC LIMIT ?
            """, (limit,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


# ──────────────────────── STATS ────────────────────────

async def get_stats():
    db = await get_db()
    try:
        stats = {}
        for table, label in [
            ("accounts", "total_accounts"),
            ("triggers", "total_triggers"),
            ("subscribers", "total_subscribers"),
            ("messages_log", "total_messages"),
            ("posts", "total_posts"),
        ]:
            cursor = await db.execute(f"SELECT COUNT(*) FROM {table}")
            row = await cursor.fetchone()
            stats[label] = row[0]

        # Bugungi xabarlar
        cursor = await db.execute(
            "SELECT COUNT(*) FROM messages_log WHERE date(created_at) = date('now')"
        )
        row = await cursor.fetchone()
        stats["today_messages"] = row[0]

        return stats
    finally:
        await db.close()
