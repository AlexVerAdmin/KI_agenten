# План развертывания проекта на VDS (Hybrid Architecture)

Данный документ содержит технические детали и план миграции проекта **Antigravity Agents** на сервер (VDS) с учетом существующей инфраструктуры (Traefik, Authelia).

---

## 🎯 Цели миграции
- Автономная работа Telegram-бота 24/7.
- Защищенный доступ к веб-интерфейсу (Streamlit) через **Authelia**.
- Синхронизация базы знаний (Obsidian) между локальным ноутом и сервером.
- Минимальное потребление ресурсов (RAM < 300MB для основных служб).

---

## 🏗 Архитектура на VDS

### 1. Docker-сервисы
- **`bot`**: Основной Python-процесс (aiogram + orchestrator).
- **`ui`**: Веб-интерфейс Streamlit.
- **`syncthing` (опционально)**: Для автоматической синхронизации папки Obsidian.

### 2. Точки входа (Traefik)
- Использование лейблов (labels) в `docker-compose.yml` для автоматического получения SSL (Let's Encrypt).
- Маршрутизация: `ai.yourdomain.com` -> Streamlit (с проверкой через Authelia Middleware).

---

## 📋 Технические заготовки (DRAFT)

### Dockerfile (Оптимизированный)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y ffmpeg libsqlite3-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Пути к данным будут монтироваться в /app/data и /app/obsidian
ENV OBSIDIAN_VAULT_PATH=/app/obsidian
ENV SQLITE_DB_PATH=/app/data/memory_v2.sqlite
```

### Структура `docker-compose.yml` (Интеграция с Traefik)
```yaml
services:
  bot:
    build: .
    command: python bot.py
    restart: always
    volumes:
      - ./data:/app/data
      - ./obsidian:/app/obsidian
    env_file: .env

  ui:
    build: .
    command: streamlit run app.py
    restart: always
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.ai-ui.rule=Host(`ai.yourdomain.com`)"
      - "traefik.http.routers.ai-ui.entrypoints=https"
      - "traefik.http.routers.ai-ui.tls=true"
      - "traefik.http.routers.ai-ui.middlewares=authelia@docker"
    volumes:
      - ./data:/app/data
      - ./obsidian:/app/obsidian
```

---

## ⚠️ Что нужно сделать перед деплоем:
1. **Синхронизация Obsidian (Syncthing)**: 
   - Я добавил Syncthing в `docker-compose.yml`. После запуска перейдите в его веб-интерфейс, добавьте папку `obsidian` и свяжите его с вашим ноутом. Папка `/app/obsidian` в боте всегда будет зеркалом вашего сейфа.
2. **Переменные окружения (.env)**: 
   - Обновите пути в `.env` на сервере: 
     `OBSIDIAN_VAULT_PATH=/app/obsidian`
     `SQLITE_DB_PATH=/app/data/memory_v2.sqlite`
3. **Безопасность (Traefik + Authelia)**: 
   - В лейблах сервера я указал подсетку `traefik-proxy` и мидлвару `authelia-auth@docker`. Убедитесь, что на сервере названия ваших сетей и мидлвар совпадают (если нет — подправьте в `docker-compose.yml`).
4. **Пути для Chromadb**:
   - База данных векторов (для памяти) также вынесена в отдельную папку `./chroma_db`, её нужно примонтировать.

## 🚀 Инструкция по запуску на VDS (AlexVerAdmin Repo):
1.  **Клонирование**: Выполните `git clone` вашего репозитория на сервер.
2.  **Папки**: В корне проекта создайте папки вручную: `mkdir data obsidian chroma_db`. Это предотвратит проблемы с правами доступа Docker (root).
3.  **Конфигурация**: 
    - Создайте файл `.env` на основе вашего локального.
    - **ОБЯЗАТЕЛЬНО**: Измените в `.env` пути:
      `OBSIDIAN_VAULT_PATH=/app/obsidian`
      `SQLITE_DB_PATH=/app/data/memory_v2.sqlite`
    - В `docker-compose.yml` замените `yourdomain.com` на ваш реальный домен.
4.  **Запуск**: `docker-compose up -d --build`.
5.  **Syncthing**:
    - Перейдите на `sync-ai.yourdomain.com` (пароль от Authelia).
    - Добавьте ваше устройство (ноутбук) и расшарьте папку `obsidian`.
    - Все ваши заметки и планы обучения Herr Max Klein появятся на сервере автоматически.

---
*Документ подготовлен GitHub Copilot для успешного деплоя проекта на VDS.*
