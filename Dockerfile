# Dockerfile (Оптимизированный для VDS с 2ГБ RAM)
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsqlite3-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ARG REQUIREMENTS_FILE=requirements.txt
COPY requirements.txt .
COPY requirements-local.txt* .
RUN pip install --no-cache-dir -r ${REQUIREMENTS_FILE}

COPY . .

# Создаем папки с нужными правами
RUN mkdir -p /app/data /app/obsidian /app/chroma_db

ENV PYTHONUNBUFFERED=1
ENV OBSIDIAN_VAULT_PATH=/app/obsidian
ENV SQLITE_DB_PATH=/app/data/memory_v2.sqlite

EXPOSE 8501
