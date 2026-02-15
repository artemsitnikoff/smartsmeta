# Деплой SmartSmeta

## Первый раз на VPS

```bash
# 1. Клонируем репо
git clone https://github.com/artemsitnikoff/smartsmeta.git
cd smartsmeta

# 2. Создаём .env
cp .env.example .env
nano .env
# Заполнить TELEGRAM_BOT_TOKEN и OPENAI_API_KEY

# 3. Запускаем
docker compose up -d --build

# 4. Проверяем
curl http://localhost:8000/health
docker compose logs -f
```

## Обновление (деплой нового кода)

```bash
cd smartsmeta
./deploy.sh
```

Или руками:

```bash
git pull origin main
docker compose up -d --build
```

## Полезные команды

```bash
# Логи бота (docker)
docker compose logs -f

# Логи бота (файл)
tail -f logs/bot.log

# Перезапуск
docker compose restart

# Остановка
docker compose down
```
