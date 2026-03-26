# yfw-statement-tools

Purpose-built workflows for YourFinanceWORKS bank statements.

Built from [yfw-plugin-template](https://github.com/snowsky/yfw-plugin-template) — runs as a
**standalone app** or as an **installed plugin** inside YFW.

## Features

- **Merge Statements** — select 2+ statements, merge into one consolidated file
  - Direct browser download (no server storage required)
  - Or upload to S3/Azure/GCS with configurable retention period

## Quick start

### Standalone mode

```bash
cp .env.example .env
# Edit .env:
#   YFW_API_URL=https://your-yfw-instance.com
#   YFW_API_KEY=ak_...

# Backend
pip install -r requirements.txt
uvicorn standalone.main:app --reload

# Frontend (new terminal)
cd ui/standalone
npm install
npm run dev
```

Open http://localhost:5173 → Setup page → enter API URL + key → Merge Statements.

### Docker Compose

```bash
cp .env.example .env
docker-compose up
```

API → http://localhost:8000 · UI → http://localhost:3000

### Plugin mode (install into YFW)

**Via YFW plugin installer:**

YFW Settings → Plugins → Install → paste this repo's GitHub URL.

**Manual:**

```bash
cd /path/to/invoice_app/api/plugins
git clone https://github.com/your-org/yfw-statement-tools statement-tools
# Restart YFW — plugin auto-discovered at /api/v1/statement-tools/
```

## API key setup

1. In YFW: **Settings → API Access → Create Key** _(requires `external_api` license feature)_
2. Copy the `ak_...` key to your `.env` as `YFW_API_KEY`

## Cloud storage (optional)

By default (`STORAGE_BACKEND=none`) merged files are streamed directly to the browser.

To save files with a retention period:

```env
STORAGE_BACKEND=s3
AWS_S3_BUCKET=my-bucket
AWS_S3_ACCESS_KEY_ID=...
AWS_S3_SECRET_ACCESS_KEY=...
FILE_RETENTION_DAYS=7     # presigned URL expires after this many days
```

Azure and GCS support are scaffolded in `shared/services/storage.py`.

## Structure

```
shared/          ← all domain logic (DRY — used by plugin + standalone)
  compat.py      ← mode-detection shim
  routers/       ← FastAPI endpoints
  schemas/       ← Pydantic models
  services/
    invoice_api_client.py  ← HTTP client for YFW API
    storage.py             ← none / S3 / Azure / GCS abstraction

standalone/      ← standalone-specific infrastructure
  config.py      ← Settings (YFW_API_URL, YFW_API_KEY, storage)
  auth.py        ← API-key validation against YFW
  main.py        ← FastAPI entry point

ui/
  shared/        ← shared React components (DRY)
    api.ts
    pages/
      MergeStatementsPage.tsx
      SetupPage.tsx
  plugin/        ← plugin frontend entry (pluginRoutes, navItems)
  standalone/    ← standalone Vite SPA (@shared → ../../ui/shared)

__init__.py      ← plugin entry: register_plugin(app)
plugin.json      ← plugin manifest
```

## License

AGPLv3
