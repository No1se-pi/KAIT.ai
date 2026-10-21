# KAIT.ai

Быстрый цифровой помощник абитуриента Колледжа автоматизации и информационных технологий №20.

Один сервис обслуживает три канала:

- Telegram-бот;
- бот MAX через защищённый webhook;
- HTTP API и встраиваемый web-виджет.

## Почему отвечает быстро

Каталог 12 программ КАИТ №20 загружается в память один раз. Типовые вопросы, подбор направления, контакты и поступление обрабатываются детерминированно без embeddings, полного сканирования PostgreSQL и ожидания LLM. PostgreSQL используется только для сессий и истории диалогов. API возвращает `latency_ms` для контроля задержки.

## Быстрый запуск

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

API и демо:

- `GET http://localhost:8000/api/health`
- `POST http://localhost:8000/ambi/v1/dialog`
- `GET http://localhost:8000/api/demo`
- OpenAPI: `http://localhost:8000/docs`

Пример запроса:

```json
{
  "user_id": "site-user-1",
  "message": "Люблю программировать, что выбрать?"
}
```

## Telegram

Укажите `TELEGRAM_BOT_TOKEN` в `.env`, затем запустите профиль:

```powershell
docker compose --profile telegram up --build -d
```

Сервис `app` запускает Telegram polling и использует то же ядро ответов, что сайт и MAX.

## MAX

Укажите в `.env`:

```env
MAX_BOT_TOKEN=...
MAX_WEBHOOK_SECRET=случайная-строка
```

Webhook: `POST https://ваш-домен/integrations/max/webhook`.

В настройках подписки MAX используйте события `message_created`, `message_callback` и `bot_started`, а также тот же secret. Production webhook должен быть доступен по HTTPS на порту 443. API MAX вызывается через актуальный домен `platform-api2.max.ru`.

## Данные

Единственный рабочий источник — `data/colleges.json`, содержащий КАИТ №20 и 12 программ набора. Изменения контактов и программ следует сверять с официальными ресурсами:

- https://priem.kait20.ru/
- https://priem.kait20.ru/specialities
- https://kait20.mskobr.ru/

## Проверка

```powershell
python -m unittest discover -s tests -v
docker compose --env-file .env.example config -q
```
