# intelligent-sales-conversion-platform

Chatbot sales berbasis AI untuk use case konversi penjualan produk skincare (soft-selling, empatik, dan terstruktur per tahap percakapan).

## Fitur Utama
- Alur percakapan sales bertahap: `greeting -> opening -> consultation -> testimony -> promo -> closing -> farewell`.
- Product knowledge ter-embed untuk produk:
  `ERHA Acneact Acne Cleanser Scrub Beta Plus (ACSBP)`.
- Soft-selling dengan pendekatan empati (tanpa hard-selling).
- Token usage per turn ditampilkan di UI:
  `input_tokens`, `output_tokens`, `total_tokens`.
- Informasi model AI per turn ditampilkan di UI (`provider/model`).

## Menjalankan Aplikasi (Docker)
### 1) Mode Local (tanpa Caddy)
```bash
cp .env.local.example .env.local
docker compose -f docker-compose.local.yml up -d --build
```

Akses local:
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8002/v1`

### 2) Mode Server (dengan Caddy reverse proxy)
```bash
cp .env.server.example .env.server
docker compose -f docker-compose.server.yml up -d --build
```

Akses server default:
- Frontend (via Caddy): `http://localhost`
- Backend API (via Caddy): `http://localhost/v1`

## Menjalankan Lokal Tanpa Docker
### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Frontend dev default proxy ke backend `http://localhost:8002`.

## Konfigurasi Environment
Salin `.env.example` ke `.env` lalu isi minimal:
- `CHATBOT_DEFAULT_LLM`
- `CHATBOT_DEFAULT_MODEL`
- API key provider yang dipakai (mis. `OPENAI_API_KEY`)

### Setup Postgres Lokal (Docker Compose)
Default `.env` sudah diarahkan ke service Postgres internal Docker:

```env
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=agentic_chatbot
POSTGRES_SSLMODE=disable
APP_DATABASE_URL=
```

Catatan:
- Jika ingin pakai DB eksternal, isi `APP_DATABASE_URL` penuh (format `postgresql+psycopg://...`).

### Setup Webhook Channels
Isi variabel channel di `.env`:

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_API_VERSION=v22.0
```

Endpoint webhook:
- Telegram: `POST /v1/channels/telegram/webhook`
- WhatsApp verify: `GET /v1/channels/whatsapp/webhook`
- WhatsApp events: `POST /v1/channels/whatsapp/webhook`

### Setup Caddy Address
Gunakan variabel ini untuk alamat/site production:

```env
CADDY_SITE_ADDRESS=:80
CADDY_HTTP_PORT=80
CADDY_HTTPS_PORT=443
CADDY_EMAIL=
```

## Catatan API Penting
- Chat endpoint:
  `POST /v1/chatbot/chat`
- Chat stream endpoint:
  `POST /v1/chatbot/chat/stream`
- Database agent endpoint:
  `POST /v1/database/query`
- Vector agent endpoint:
  `POST /v1/vector/search`
- Billing summary endpoint:
  `GET /v1/billing/summary/{user_id}`
- Stream akan mengirim event `meta` berisi:
  - stage percakapan
  - model identity
  - token usage per turn
