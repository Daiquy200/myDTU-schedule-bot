# Hướng dẫn deploy Serverless Telegram Bot

## Kiến trúc

```
Telegram → Webhook → Serverless Function (FastAPI) → Database
                                      ↓
                              PDF Parser (pdfplumber)
```

## Tính năng chính

- ✅ Multi-user: Mỗi user có lịch riêng (lọc theo `user_id`)
- ✅ Nhận PDF, phân tích tự động (pdfplumber)
- ✅ Xác nhận trước khi lưu: Thay thế / Cộng thêm / Hủy
- ✅ Các lệnh: `/start`, `/today`, `/tomorrow`, `/week`, `/next`, `/lich`, `/delete`, `/help`
- ✅ Hỏi ngôn ngữ tự nhiên: "hôm nay", "ngày mai", "tuần này", "thứ 2"...
- ✅ Serverless: Chỉ chạy khi có request, không cần VPS 24/7
- ✅ Database: SQLite (local) hoặc PostgreSQL (production)

---

## 1. Local Development

### Cài đặt

```bash
cd serverless_bot
pip install -r requirements.txt
```

### Chạy local (polling mode)

```bash
# Tạo file .env từ .env.example
cp .env.example .env
# Sửa TELEGRAM_BOT_TOKEN trong .env

# Chạy
python run_local.py
```

---

## 2. Deploy lên Vercel (Khuyên dùng - Free tier)

### Chuẩn bị

1. Push code lên GitHub
2. Tạo project trên Vercel, import repo

### Cấu hình Environment Variables trên Vercel

| Variable | Giá trị |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Token bot từ BotFather |
| `DATABASE_URL` | PostgreSQL connection string (Supabase/Neon/Railway) |

### Database PostgreSQL (Free)

**Supabase (Khuyên dùng):**
1. Tạo project tại supabase.com
2. Settings → Database → Connection string → URI
3. Copy connection string, thêm vào Vercel env `DATABASE_URL`

**Neon:**
1. Tạo project tại neon.tech
2. Copy connection string

### Cài đặt Webhook sau deploy

Sau khi deploy xong (giả sử URL: `https://your-app.vercel.app`):

```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-app.vercel.app/webhook"}'
```

Hoặc dùng script:
```bash
WEBHOOK_URL=https://your-app.vercel.app/webhook
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"$WEBHOOK_URL\"}"
```

### Kiểm tra webhook
```bash
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo"
```

---

## 3. Deploy lên Cloudflare Workers (Python Workers)

### Yêu cầu
- Cloudflare account
- Wrangler CLI: `npm install -g wrangler`

### Cấu hình wrangler.toml
```toml
name = "telegram-schedule-bot"
main = "src/main.py"
compatibility_date = "2024-01-01"

[vars]
TELEGRAM_BOT_TOKEN = "your_token"

[[d1_databases]]
binding = "DB"
database_name = "schedule-db"
database_id = "your-d1-id"
```

> Lưu ý: Cloudflare Workers Python hỗ trợ D1 (SQLite) qua binding, cần điều chỉnh code database layer.

---

## 4. Deploy lên Railway / Render / Fly.io (Container)

### Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Railway
1. Connect GitHub repo
2. Add `TELEGRAM_BOT_TOKEN` và `DATABASE_URL` (PostgreSQL)
3. Deploy → Get URL → Set webhook

---

## 5. Database Schema

### SQLite (Local)
```sql
-- Tự tạo khi chạy lần đầu
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    first_name TEXT,
    username TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    day_of_week INTEGER,
    start_time TEXT,
    end_time TEXT,
    subject TEXT,
    subject_code TEXT,
    class_code TEXT,
    room TEXT,
    lecturer TEXT,
    week_range TEXT,
    learning_type TEXT,
    note TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_schedules_user_date ON schedules(user_id, date);
```

### PostgreSQL (Production)
```sql
CREATE TABLE users (
    user_id BIGINT PRIMARY KEY,
    first_name TEXT,
    username TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE schedules (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    date DATE NOT NULL,
    day_of_week SMALLINT,
    start_time TIME,
    end_time TIME,
    subject TEXT,
    subject_code TEXT,
    class_code TEXT,
    room TEXT,
    lecturer TEXT,
    week_range TEXT,
    learning_type TEXT,
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_schedules_user_date ON schedules(user_id, date);
```

---

## 6. Chi phí ước tính (Free tier)

| Dịch vụ | Free tier |
|---------|-----------|
| Telegram Bot API | Miễn phí |
| Vercel Functions | 100GB-hours/tháng |
| Supabase PostgreSQL | 500MB DB, 1GB transfer |
| Neon PostgreSQL | 512MB storage |
| Cloudflare Workers | 100k requests/ngày |
| Railway | $5 credit/tháng |

**Tổng chi phí: 0đ** cho sử dụng cá nhân.

---

## 7. Test PDF Parser

```bash
cd serverless_bot
python -m parser.parse_pdf "path/to/your/schedule.pdf"
```

Output JSON với danh sách các buổi học có date, time, subject, room...

---

## 8. Cấu trúc thư mục

```
serverless_bot/
├── main.py                 # FastAPI app (webhook endpoint)
├── run_local.py            # Local polling runner
├── requirements.txt
├── vercel.json             # Vercel config
├── .env.example            # Template env
├── DEPLOY.md               # File này
├── db/
│   ├── __init__.py
│   └── database.py         # Database layer (SQLite + PostgreSQL)
├── handlers/
│   ├── __init__.py
│   └── bot_handlers.py     # Telegram handlers
├── parser/
│   ├── __init__.py
│   └── parse_pdf.py        # PDF parser (pdfplumber)
└── utils/
    └── __init__.py
```

---

## 9. Troubleshooting

### Bot không phản hồi
- Kiểm tra webhook URL đúng chưa: `getWebhookInfo`
- Xem log Vercel/Cloudflare
- Test manual: `curl -X POST <webhook_url> -H "Content-Type: application/json" -d '{"update_id":1,"message":{"message_id":1,"from":{"id":123,"is_bot":false,"first_name":"Test"},"chat":{"id":123,"type":"private"},"date":1234567890,"text":"/start"}}'`

### Lỗi database
- Local: Xóa file `schedule.db` để reset
- Production: Kiểm tra `DATABASE_URL` format đúng

### PDF không parse được
- PDF phải là text-based (không phải scan ảnh)
- Thử file PDF mẫu trong repo
- Cần OCR cho PDF scan → dùng paddleocr/tesseract

---

## 10. Mở rộng tương lai

- [ ] Nhắc lịch tự động (cron job / Cloudflare Scheduled)
- [ ] Xuất Google Calendar / iCal
- [ ] AI xử lý PDF phức tạp (Gemini/GPT API)
- [ ] Multi-language support
- [ ] Admin panel quản lý user