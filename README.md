# Intelligent Sales Conversion Platform

An AI-powered sales chatbot platform focused on skincare conversion flows.

The system combines a FastAPI backend, a React frontend, multi-agent orchestration, channel webhooks (Telegram and WhatsApp), usage billing analytics, and Docker-based local/server deployment.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Core Features](#core-features)
- [Tech Stack](#tech-stack)
- [Repository Structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Environment Configuration](#environment-configuration)
- [Run with Docker](#run-with-docker)
- [Run without Docker](#run-without-docker)
- [API Reference](#api-reference)
- [Channel Webhook Setup](#channel-webhook-setup)
- [Billing and Model Tracking](#billing-and-model-tracking)
- [Deployment Notes (Caddy)](#deployment-notes-caddy)
- [Troubleshooting](#troubleshooting)
- [Known Limitations](#known-limitations)

## Overview

This project is designed for guided sales conversations with stage-aware responses:

`greeting -> opening -> consultation -> testimony -> promo -> closing -> farewell`

The backend persists conversations, tracks token usage and estimated cost per model, and exposes webhook endpoints for external chat channels.

## Architecture

```text
Frontend (React + Vite, Nginx in Docker)
  -> /v1/* API calls
Backend (FastAPI)
  -> Planner agent (LLM)
  -> Memory agent (LLM)
  -> Database agent (product facts from PostgreSQL)
  -> Vector agent (lightweight lexical retrieval from product knowledge)
  -> Billing usage event recorder (per provider/model)
PostgreSQL
  -> conversations, messages, history
  -> admin configs/prompts
  -> billing events
  -> memory entries
  -> seeded sales product
Channels
  -> Telegram webhook
  -> WhatsApp webhook
Reverse Proxy (Server mode)
  -> Caddy (TLS + host-based routing)
```

## Core Features

- Stage-based sales conversation orchestration.
- Multi-provider LLM support (OpenAI, Anthropic, Google, xAI).
- Admin-configurable model selection per agent.
- Prompt override management from UI/API.
- Conversation persistence and history management.
- Billing dashboard with:
  - total input/output/total tokens
  - estimated USD cost
  - daily cost and token charts
  - per-model breakdown that remains accurate after model switching
- Telegram and WhatsApp webhook integrations.
- Channel UX enhancements:
  - typing indicator
  - testimony-triggered image attachment

## Tech Stack

- Backend: FastAPI, SQLModel, Pydantic, Uvicorn
- Database: PostgreSQL
- Frontend: React 19, Vite
- Reverse Proxy (server mode): Caddy 2
- Containerization: Docker Compose

## Repository Structure

```text
backend/
  app/
    agents/
    channels/
    core/
    modules/
  tests/
frontend/
  src/
Caddyfile
docker-compose.local.yml
docker-compose.server.yml
.env.example
```

## Prerequisites

- Docker + Docker Compose
- Or for non-Docker run:
  - Python 3.11+
  - Node.js 20+
  - PostgreSQL 14+

## Environment Configuration

The backend always loads environment variables from the project root `.env`.

1. Copy template:

```bash
cp .env.example .env
```

2. Fill the required values.

### Required Variables

| Variable | Required | Description |
|---|---|---|
| `CHATBOT_DEFAULT_LLM` | Yes | Default provider (`openai`, `anthropic`, `google`, `xai`) |
| `CHATBOT_DEFAULT_MODEL` | Yes | Default model name |
| Provider API key | Yes | At least one key for the provider you use (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.) |
| `POSTGRES_HOST` | Yes* | DB host if `APP_DATABASE_URL` is empty |
| `POSTGRES_PORT` | Yes* | DB port |
| `POSTGRES_USER` | Yes* | DB user |
| `POSTGRES_PASSWORD` | Yes* | DB password |
| `POSTGRES_DB` | Yes* | DB name |

`*` Required when `APP_DATABASE_URL` is not set.

### Optional Variables

| Variable | Purpose |
|---|---|
| `APP_DATABASE_URL` | Full DB URL override (`postgresql+psycopg://...`) |
| `POSTGRES_SSLMODE` | Appended to derived URL (for managed DB SSL settings) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot API token |
| `TELEGRAM_WEBHOOK_SECRET` | Secret header validation (`X-Telegram-Bot-Api-Secret-Token`) |
| `WHATSAPP_VERIFY_TOKEN` | Webhook verification token (Meta callback handshake) |
| `WHATSAPP_ACCESS_TOKEN` | Required for sending WhatsApp replies |
| `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp Cloud API phone number id |
| `WHATSAPP_API_VERSION` | Defaults to `v22.0` |

### Legacy/Reserved Variables in `.env.example`

`VECTORDB_*`, `WEB_SEARCH_*`, and `CADDY_*` are currently placeholders and are not consumed by active backend runtime in this codebase version.

## Run with Docker

### Local Mode (no Caddy)

```bash
docker compose -f docker-compose.local.yml up -d --build
```

Access:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8002`
- API docs: `http://localhost:8002/docs`

Stop:

```bash
docker compose -f docker-compose.local.yml down
```

### Server Mode (with Caddy reverse proxy)

```bash
docker compose -f docker-compose.server.yml up -d --build
```

Default domain mapping in `Caddyfile`:

- `dashboard.isanmas.site` -> frontend
- `api.isanmas.site` -> backend

Before running on your server:

- Update domains in `Caddyfile`.
- Update `frontend` build arg `VITE_API_URL` in `docker-compose.server.yml` if you change API domain.
- Point DNS A/AAAA records to your server IP.
- Open ports `80` and `443`.

## Run without Docker

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Vite dev server runs at `http://localhost:3000` and proxies `/v1` to `http://localhost:8002`.

## API Reference

Base URL:

- Local Docker: `http://localhost:8002`
- Server: `https://api.your-domain.tld`

Interactive docs:

- `/docs`
- `/redoc`

### Chatbot Endpoints

- `POST /v1/chatbot/chat`
- `POST /v1/chatbot/chat/stream` (SSE)
- `GET /v1/chatbot/conversations/{user_id}`
- `POST /v1/chatbot/conversations/{user_id}`
- `GET /v1/chatbot/conversations/{user_id}/{conversation_id}`
- `DELETE /v1/chatbot/conversations/{user_id}/{conversation_id}`
- `PATCH /v1/chatbot/conversations/{user_id}/{conversation_id}/title`
- `POST /v1/chatbot/conversations/{user_id}/{conversation_id}/messages`
- `GET /v1/chatbot/history/{user_id}`
- `DELETE /v1/chatbot/history/{user_id}`

Example request:

```bash
curl -s -X POST http://localhost:8002/v1/chatbot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Jerawat meradang dan berminyak, cocok pakai apa?",
    "history": [],
    "user_id": "0"
  }'
```

Example stream request:

```bash
curl -N -X POST http://localhost:8002/v1/chatbot/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Boleh testimoni real user?",
    "history": [],
    "user_id": "0",
    "conversation_id": "<conversation-id>"
  }'
```

SSE event types include: `thinking`, `content`, `meta`, `done`.

### Admin Endpoints

- `GET /v1/admin/configs`
- `PUT /v1/admin/configs`
- `GET /v1/admin/prompts`
- `PUT /v1/admin/prompts/{slug}`
- `GET /v1/admin/llm/options`

### Billing Endpoints

- `GET /v1/billing/summary/{user_id}?days=30&recent_limit=60`
- `GET /v1/billing/events/{user_id}?days=30&limit=200`

### Database Agent Endpoints

- `POST /v1/database/query`
- `POST /v1/database/query/stream` (SSE)

### Vector Agent Endpoints

- `POST /v1/vector/search`
- `POST /v1/vector/search/stream` (SSE)

### Channel Endpoints

- Telegram: `POST /v1/channels/telegram/webhook`
- WhatsApp verify: `GET /v1/channels/whatsapp/webhook`
- WhatsApp events: `POST /v1/channels/whatsapp/webhook`

## Channel Webhook Setup

### Telegram

Required env:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`

Register webhook (Linux/macOS):

```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://api.your-domain.tld/v1/channels/telegram/webhook",
    "secret_token": "<TELEGRAM_WEBHOOK_SECRET>"
  }'
```

Register webhook (Windows PowerShell):

```powershell
curl.exe -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" `
  -H "Content-Type: application/json" `
  -d "{\"url\":\"https://api.your-domain.tld/v1/channels/telegram/webhook\",\"secret_token\":\"<TELEGRAM_WEBHOOK_SECRET>\"}"
```

### WhatsApp (Meta Cloud API)

Required env:

- `WHATSAPP_VERIFY_TOKEN` (for webhook verification handshake)
- `WHATSAPP_ACCESS_TOKEN` (for sending replies)
- `WHATSAPP_PHONE_NUMBER_ID`

Important:

- `WHATSAPP_VERIFY_TOKEN` is only for webhook verification.
- Reply sending requires a valid, non-expired `WHATSAPP_ACCESS_TOKEN`.
- If logs show `401 Unauthorized`, your access token is invalid/expired or has missing permissions.

Meta webhook configuration:

- Callback URL: `https://api.your-domain.tld/v1/channels/whatsapp/webhook`
- Verify token: must exactly match `.env` `WHATSAPP_VERIFY_TOKEN`

## Billing and Model Tracking

Billing is tracked per request event using provider/model metadata from assistant responses.

Why model-switch tracking still works:

- Every usage event stores `provider` and `model` explicitly.
- Billing summary aggregates per model (`by_model`) instead of assuming one global active model.
- Historical events remain intact even if default models are changed later in Admin settings.

Costing details:

- Estimated USD cost is calculated from token counts using per-model/per-provider pricing maps in `backend/app/modules/billing/service.py`.
- Pricing source is marked as `exact`, `prefix`, or `provider_default`.

## Deployment Notes (Caddy)

Current `Caddyfile` is host-based and static. Update domains before production use.

Example mapping:

```caddy
my-dashboard.example.com {
  reverse_proxy frontend:80
}

my-api.example.com {
  reverse_proxy backend:8000
}
```

After changing domains:

1. Update `Caddyfile`.
2. Update `VITE_API_URL` build arg in `docker-compose.server.yml`.
3. Rebuild and restart:

```bash
docker compose -f docker-compose.server.yml up -d --build
```

## Troubleshooting

### Docker error: `open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified`

Docker Desktop Linux engine is not running. Start Docker Desktop and retry.

### Startup error: `Database configuration is missing`

Set either:

- `APP_DATABASE_URL`, or
- complete `POSTGRES_*` values.

### DB host resolution error (managed DB/Supabase)

Verify the hostname in your database URL. Placeholder hosts (for example `project-ref` style) will fail.

### Telegram webhook returns 403

`TELEGRAM_WEBHOOK_SECRET` does not match `X-Telegram-Bot-Api-Secret-Token`.

### WhatsApp replies fail with 401

Refresh `WHATSAPP_ACCESS_TOKEN`, verify app permissions, and confirm `WHATSAPP_PHONE_NUMBER_ID`.

### Channel testimony image does not show

The channel code sends remote image URLs. If your provider rejects a URL, check backend logs for image send failures and replace blocked URLs.

## Known Limitations

- No authentication layer in frontend/backend by default. Frontend currently uses a fixed demo user id (`"0"`).
- CORS is permissive (`allow_origins=["*"]`) and should be hardened for production.
- Existing test suite is partially outdated against current API contracts and may fail without test updates.
- Vector agent is currently a lightweight lexical retriever over sales knowledge, not an external vector database integration.

