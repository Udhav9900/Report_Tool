# ---------- 1. Build the React website ----------
FROM node:22-slim AS website
WORKDIR /web
COPY Frontend/my-app/package*.json ./
RUN npm ci
COPY Frontend/my-app/ ./
RUN npm run build

# ---------- 2. Python backend that also serves the website ----------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app

COPY Backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY Backend/ ./
COPY --from=website /web/dist ./static
RUN python -m reports_.build_template

# Railway (and most hosts) tell the app which port to use through $PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]