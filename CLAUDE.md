# TimeMirror — CLAUDE.md

## Что это
Telegram-бот для учёта времени. Python 3.12, aiogram 3.x, FastAPI, PostgreSQL 16, Google Sheets, DeepSeek AI.
Репозиторий: https://github.com/iRatG/Tmmngr.git (branch: master)

## VPS
- root@83.222.22.95, Ubuntu 24.04
- SSH hostkey: SHA256:O6BRkVyzk/T5LzU9SZ9z7Oh1T70E7c32RrCMV//D/m8
- Project: /opt/timemirror
- Container: timemirror-app-1

## Подключение из Windows (MSYS2)
```bash
# SSH
MSYS_NO_PATHCONV=1 plink -ssh root@83.222.22.95 -pw "PASSWORD" -hostkey "SHA256:..." "command"

# Загрузка файла
MSYS_NO_PATHCONV=1 pscp -pw "PASSWORD" -hostkey "SHA256:..." "c:/tg_tracker/file.py" root@83.222.22.95:/opt/timemirror/file.py
```

## Рабочий процесс (каждая сессия)
1. Написать файлы локально в `c:\tg_tracker\`
2. Загрузить через base64 (см. ниже — pscp ненадёжен для Python файлов)
3. `docker compose build app && docker compose up -d app` (nohup, ждать ~70 сек)
4. Проверить логи: `docker logs timemirror-app-1 --tail 10`
5. Запустить тесты если нужно
6. `git add + commit + push` (НЕ в фоне — через прямой plink)

## Загрузка Python файлов на VPS (ОБЯЗАТЕЛЬНЫЙ СПОСОБ)
pscp ненадёжен: обрывает соединение и зануляет файл. Использовать base64:
```bash
# 1. Локально — убедиться что файл ASCII (убрать em dash, box chars)
python3 -c "import base64; data=open('c:/tg_tracker/file.py','rb').read(); [print(i,b) for i,b in enumerate(data) if b>127]"

# 2. Если ASCII — можно через plink echo (файлы до ~4KB):
B64=$(python3 -c "import base64; print(base64.b64encode(open('c:/tg_tracker/file.py','rb').read()).decode())")
MSYS_NO_PATHCONV=1 plink ... "echo '$B64' > /tmp/b64.txt && python3 -c \"import base64; open('/opt/timemirror/file.py','wb').write(base64.b64decode(open('/tmp/b64.txt').read().strip()))\" && wc -c /opt/timemirror/file.py"

# 3. Если non-ASCII — через pscp txt файл (ASCII txt безопасен):
python3 -c "import base64; open('c:/tg_tracker/tmp_b64.txt','w').write(base64.b64encode(open('c:/tg_tracker/file.py','rb').read()).decode())"
pscp ... "c:/tg_tracker/tmp_b64.txt" root@host:/tmp/b64.txt
plink ... "python3 -c \"import base64; open('/opt/timemirror/file.py','wb').write(base64.b64decode(open('/tmp/b64.txt').read()))\""
```
Проверять результат: `wc -c /opt/timemirror/file.py` — должен совпадать с локальным размером.

## Критические правила

### Параллельный pscp — НЕЛЬЗЯ для одинаковых имён файлов
Параллельный upload через `&` нескольких файлов с одинаковым именем зануляет файл.
Файлы с РАЗНЫМИ именами — можно параллельно. Файлы с одинаковым именем — строго последовательно.

### Длинные команды зависают в plink
Команды дольше ~15 сек зависают. Паттерн:
```bash
nohup docker exec timemirror-app-1 python script.py > /tmp/out.txt 2>&1 &
sleep 20 && cat /tmp/out.txt
```

### git commit — только однострочные сообщения
Многострочные (heredoc) зависают в plink. Только: `git commit -m 'one line'`

### Новые файлы не попадают в контейнер автоматически
После `docker compose up` нужно делать `docker cp` для каждого нового файла.
Полный rebuild только в финальной сессии.

### Удаление тестовых данных — порядок FK
```
activity_logs → daily_aggregates → categories → user_settings → users
```

### gspread синхронный
Всегда оборачивать: `await asyncio.to_thread(google_sheets.func, args)`

## Архитектура модулей
```
bot/
  keyboards.py          — все клавиатуры
  messages.py           — все тексты
  handlers/
    onboarding.py       — /start, FSM подключения Google Sheet
    activity.py         — начать/завершить блок
    reminder.py         — кнопки напоминания
    status.py           — "📊 Сегодня" (сессия 8)
    user_settings.py    — "⚙️ Настройки" (сессия 8)

db/
  models.py             — 8 SQLAlchemy моделей
  session.py            — AsyncSessionFactory
  repositories/
    user_repo.py
    category_repo.py
    activity_repo.py

services/
  activity_service.py   — start_block, finish_block, sync_log_to_sheet
  reminder_service.py   — отправка напоминаний (scheduler job)
  analytics_service.py  — агрегаты, today_stats, week_stats
  summary_service.py    — DeepSeek вечерний/недельный отчёт
  sheets_sync_service.py — pull правок из Sheets → DB

scheduler/
  jobs.py               — APScheduler: reminder(1min), daily(23:55), evening(18:00), weekly(sun 17:00), sheets_pull(30min)

integrations/
  google_sheets.py      — extract_id, init_spreadsheet, write, read

migrations/
  env.py                — Alembic async
```

## Статус сессий
| # | Что | Статус |
|---|-----|--------|
| 1 | VPS + Docker + nginx | DONE |
| 2 | Foundation + DB + Alembic | DONE |
| 3 | keyboards + messages + onboarding + google_sheets | DONE |
| 4 | activity repo + service + handlers | DONE |
| 5 | reminder + scheduler | DONE |
| 6 | analytics + DeepSeek summary | DONE |
| 7 | sheets_sync pull | DONE |
| 8 | status handler + settings + main.py | DONE |
| 9 | rebuild + webhook + e2e test | DONE |

**Бот живой.** POST /webhook → 200 OK. Scheduler: 5 jobs.

## Тесты
- `test_infra.py` — инфраструктура (DB connection, 8 таблиц, CRUD, /health) → 16/16
- `test_logic.py` — бизнес-логика (URL parsing, categories, user flow, analytics) → 26/26

## Уроки сессии 9 (nginx + Telegram webhook)

### nginx SSL не был включён по умолчанию
После сессии 1 nginx слушал только :80. Пришлось создать `/etc/nginx/sites-available/timemirror`:
```nginx
server {
    listen 443 ssl;
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    location / { proxy_pass http://127.0.0.1:8000; }
}
server { listen 80; return 301 https://$host$request_uri; }
```
Затем: `ln -s ... sites-enabled`, удалить default, `nginx -t && nginx -s reload`.

### Telegram webhook с самоподписанным SSL — нужно загрузить сертификат
```bash
curl -F "url=https://IP/webhook" \
  -F "certificate=@/etc/nginx/ssl/cert.pem" \
  "https://api.telegram.org/bot<TOKEN>/setWebhook"
```
Без `-F certificate=` Telegram возвращает SSL verify error и не присылает обновления.
Проверка: `getWebhookInfo` → `has_custom_certificate: true`, нет `last_error_message`.

## Баги и исправления (пост-деплой, после сессии 9)

### Баг 1: /start не предлагал подключить таблицу повторно
**Симптом:** пользователь есть в БД, но таблица не привязана — /start говорил "Привет снова!" и всё.
**Причина:** `cmd_start` в `onboarding.py` при `not created` сразу возвращал меню без проверки GoogleConnection.
**Фикс:** добавлена проверка активного GoogleConnection. Если нет — снова запрашиваем ссылку.
**Файл:** `bot/handlers/onboarding.py`, коммит `d42fdd9`

### Баг 2: Webhook слетал после каждого рестарта контейнера
**Симптом:** после `docker compose up`, `getWebhookInfo` показывал `has_custom_certificate: false` + SSL error. Бот не получал сообщения.
**Причина:** `on_startup` в `main.py` вызывал `set_webhook` без передачи сертификата — Telegram перезаписывал регистрацию без cert.
**Фикс:** `main.py` читает `/app/ssl/cert.pem` и передаёт в `set_webhook`. `docker-compose.yml` монтирует `/etc/nginx/ssl/cert.pem:/app/ssl/cert.pem:ro`.
**Файлы:** `main.py`, `docker-compose.yml`, коммит `f30bd67`

### Баг 3: Google Sheets не подключались
**Симптом:** бот отвечал "Не удалось подключиться к таблице" при любой ссылке.
**Причина:** в `.env` путь к credentials был хостовый (`/opt/timemirror/google_credentials.json`), а в контейнере файл монтируется в `/app/google_credentials.json`.
**Фикс:** исправлен `.env` на сервере: `GOOGLE_SERVICE_ACCOUNT_JSON=/app/google_credentials.json`
**Важно:** `.env` не в git — при пересоздании сервера нужно исправить вручную.

### Баг 4: pscp зануляет файлы при обрыве соединения
**Симптом:** pscp показывает 100%, но файл на VPS = 0 байт. Контейнер не стартует: `module has no attribute 'router'`.
**Причина:** pscp truncates файл перед записью. При обрыве — файл остаётся пустым.
**Фикс:** использовать base64 через plink echo (см. раздел "Загрузка Python файлов").
