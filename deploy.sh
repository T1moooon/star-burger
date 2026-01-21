#!/usr/bin/env bash
set -e

# Переходим в директорию проекта
cd "$(dirname "$0")"

echo "[1] Обновление кода"
git pull origin main

echo "[2] Остановка старых контейнеров"
docker compose down --remove-orphans

echo "[3] Сборка фронтенда"
docker compose run --rm frontend

echo "[4] Запуск контейнеров (кроме backend)"
docker compose up -d db

echo "[5] Ожидание БД"
# Ждем пока база будет готова. В docker-compose.yml есть healthcheck.
until [ "$(docker compose ps -q db | xargs docker inspect -f '{{.State.Health.Status}}' 2>/dev/null)" == "healthy" ]; do
    echo "Ожидание готовности базы данных..."
    sleep 2
done

# Загружаем переменные из .env для работы с БД и Rollbar
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

echo "[6] Запускаем остальные сервисы"
docker compose up -d --build

echo "[7] Миграции и статика"
docker compose exec -T backend python manage.py migrate --noinput
docker compose exec -T backend python manage.py collectstatic --noinput

echo "[8] Перезапуск nginx"
docker compose exec -T nginx nginx -s reload

echo "[9] Уведомление Rollbar"
REVISION=$(git rev-parse HEAD)
USERNAME=$(whoami)

if [ -n "$ROLLBAR_ACCESS_TOKEN" ]; then
    curl -H "X-Rollbar-Access-Token: $ROLLBAR_ACCESS_TOKEN" \
         -X POST 'https://api.rollbar.com/api/1/deploy' \
         -d environment="$ROLLBAR_ENVIRONMENT" \
         -d revision="$REVISION" \
         -d local_username="$USERNAME"
    echo "Уведомление в Rollbar отправлено"
else
    echo "ROLLBAR_ACCESS_TOKEN не найден, пропускаем уведомление"
fi

echo "Готово"
docker compose ps
