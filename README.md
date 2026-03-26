# yfw-statement-tools

A simplified upload portal for bank statements:
1. **Upload** one or more CSV/PDF bank statements.
2. **AI Processing** — files are forwarded to YourFinanceWORKS for OCR/AI extraction.
3. **Merge & Download** — results are consolidated into a single CSV with a 1-hour download link.

## Quick Start

### Standalone Mode

```bash
# Backend
pip install -r requirements.txt
uvicorn standalone.main:app --reload

# Frontend (new terminal)
cd ui/standalone
npm install
npm run dev
```

Open http://localhost:5173 → Setup page → enter YFW URL + API key → Upload Statements.

### Docker Compose

```bash
docker-compose up
```

API → http://localhost:8000 · UI → http://localhost:3000

## API Key Setup

1. In YourFinanceWORKS: **Settings → API Access → Create Key**
2. In this app: Go to the **Setup** page and enter the API URL and Key.

## Structure

```
shared/
  routers/       ← FastAPI endpoints (upload & download)
  schemas/       ← Pydantic models
  services/
    invoice_api_client.py  ← HTTP client for YFW API

standalone/      ← Standalone infra
  config.py      ← Settings (YFW URL/Key, download expiry)
  auth.py        ← API-key validation cache
  main.py        ← FastAPI entry point & cleanup task

ui/
  shared/        ← Shared React components
    api.ts       ← Upload & setup helpers
    pages/
      SetupPage.tsx
      UploadStatementsPage.tsx
  standalone/    ← Vite SPA
```

## License

AGPLv3
