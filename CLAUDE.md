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
2. pscp → VPS `/opt/timemirror/`
3. `docker cp` → `timemirror-app-1:/app/`
4. Проверить импорты через `nohup docker exec ... python -c 'import ...' > /tmp/out.txt 2>&1 & sleep 10 && cat /tmp/out.txt`
5. Запустить тесты (test_logic.py или test_infra.py)
6. `git add + commit + push` (НЕ в фоне — через прямой plink)

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
| 8 | status handler + settings + main.py | NEXT |
| 9 | rebuild + webhook + e2e test | TODO |

## Тесты
- `test_infra.py` — инфраструктура (DB connection, 8 таблиц, CRUD, /health) → 16/16
- `test_logic.py` — бизнес-логика (URL parsing, categories, user flow, analytics) → 26/26
