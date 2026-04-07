FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source and repo-root plugin.json (build context = repo root)
COPY backend/ .
COPY plugin.json .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
