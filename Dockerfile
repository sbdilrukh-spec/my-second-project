# syntax=docker/dockerfile:1.6

# ---------- Stage 1: build frontend ----------
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend

# Сначала только package*.json — это даёт docker-кэш для npm install,
# когда исходники меняются, а пакеты — нет.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build


# ---------- Stage 2: python backend + готовая статика ----------
FROM python:3.11-slim

# Основные системные пакеты — matplotlib иногда требует libfreetype/libpng,
# slim-образ их не имеет. Минимальный набор:
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libfreetype6 \
        libpng16-16 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Сначала зависимости — для кэша
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Потом исходники
COPY backend/ ./backend/

# И собранный фронт из первого этапа
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Render передаёт PORT через ENV, run.py его читает
EXPOSE 8000
WORKDIR /app/backend
CMD ["python", "run.py"]
