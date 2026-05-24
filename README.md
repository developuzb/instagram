# 🤖 Instagram Chatbot — Admin Panel

Instagram'da kommentariyalarga avtomatik DM yuboruvchi chatbot. ManyChat'ning o'zingiznikiga o'xshashi!

## ✨ Funksiyalar

- 💬 **Comment Trigger** — Post kommentariyasida "+" yoki kalit so'z yozilganda bot ishga tushadi
- 📩 **Auto DM** — Foydalanuvchiga avtomatik Direct Message yuboradi  
- 👥 **Obunachlar bazasi** — Barcha murojaat qilgan foydalanuvchilar saqlanadi
- 📊 **Admin Panel** — Chiroyli web interfeys orqali boshqarish
- 📝 **Log** — Barcha yuborilgan xabarlar tarixi
- 🔧 **Ko'p akkaunt** — Bir vaqtda bir nechta Instagram akkaunt boshqarish

## 🚀 O'rnatish

### 1. Python o'rnatish
Python 3.10+ versiyasi kerak: https://python.org/downloads

### 2. Loyihani ishga tushirish
```
start.bat faylini ikki marta bosing
```

Yoki qo'lda:
```bash
cd backend
pip install -r requirements.txt
copy .env.example .env
# .env faylini tahrirlang
python main.py
```

### 3. Admin Panelga kirish
Browser'da ochib: **http://localhost:8000**

Default parol: `admin123` (`.env` faylida o'zgartiring!)

## ⚙️ Sozlash

### .env fayli
```env
META_APP_ID=123456789          # Facebook App ID
META_APP_SECRET=abc123...      # App Secret
WEBHOOK_VERIFY_TOKEN=mysecret  # Xohlagan maxfiy so'z
PAGE_ACCESS_TOKEN=EAAxxxx...   # Facebook Page Access Token
ADMIN_PASSWORD=admin123        # Admin parol
PORT=8000
```

### Page Access Token olish

1. **https://developers.facebook.com/apps** ga kiring
2. Yangi App yarating (Business tipida)
3. Products → Add Product → **Messenger** va **Instagram** qo'shing
4. **Graph API Explorer** ga o'ting: https://developers.facebook.com/tools/explorer/
5. Quyidagi permissionlarni tanlang:
   - `pages_messaging`
   - `instagram_manage_messages`  
   - `instagram_manage_comments`
   - `instagram_basic`
   - `pages_read_engagement`
6. "Generate Access Token" tugmasini bosing
7. Tokenni `.env` fayliga va Admin Panel → Akkauntlar ga kiriting

### Webhook sozlash

Instagram webhook'lari ishlashi uchun server internetda ochiq bo'lishi kerak.

**Mahalliy test uchun (ngrok):**
```bash
# Yuklab oling: https://ngrok.com
ngrok http 8000
# Chiqadigan URL: https://xxxx.ngrok.io
```

**Meta Developer Console'da:**
1. App → Webhooks
2. Instagram → Subscribe
3. Callback URL: `https://xxxx.ngrok.io/webhook`
4. Verify Token: `.env` dagi `WEBHOOK_VERIFY_TOKEN`
5. Subscribe: `comments`, `messages`

## 💡 Ishlatish

1. **Akkaunt qo'shing** → Page Access Token kiriting
2. **Trigger yarating** → Kalit so'z: `+`, DM: "Salom! Manzilimiz: ..."
3. **Post qo'shing** → Kuzatiladigan post URL sini kiriting
4. **Webhook sozlang** → ngrok URL va Verify Token ni Meta'ga kiriting
5. **Test qiling** → Postga "+" kommentariya yozing → DM kelishini kuting!

## 📁 Loyiha tuzilmasi

```
instagram-chatbot/
├── backend/
│   ├── main.py           # FastAPI server + webhook handler
│   ├── database.py       # SQLite ma'lumotlar bazasi
│   ├── instagram_api.py  # Meta Graph API
│   ├── requirements.txt
│   └── .env              # Sozlamalar (yarating!)
├── frontend/
│   ├── index.html        # Admin panel
│   └── static/
│       ├── style.css
│       └── app.js
├── start.bat             # Windows uchun ishga tushirish
└── README.md
```

## 🔐 Xavfsizlik

- `.env` faylini hech qachon Git'ga upload qilmang
- `PAGE_ACCESS_TOKEN` ni maxfiy saqlang
- `ADMIN_PASSWORD` ni murakkab qiling
- Production'da HTTPS ishlatish shart

## 📞 Texnik talablar

- Python 3.10+
- Instagram Business yoki Creator akkaunt
- Facebook Page (Instagram'ga ulangan)
- Meta Developer App
- Internet orqali ochiq server (webhook uchun)
