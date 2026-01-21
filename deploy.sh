#!/usr/bin/env bash
set -e

# Переходим в директорию проекта
cd "$(dirname "$0")"

COMPOSE_FILE=${COMPOSE_FILE:-docker-compose.prod.yml}
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "Файл compose не найден: $COMPOSE_FILE"
    exit 1
fi

compose() {
    docker compose -f "$COMPOSE_FILE" "$@"
}

echo "[1] Обновление кода"
git pull origin main

echo "[2] Остановка старых контейнеров"
compose down --remove-orphans

echo "[3] Сборка фронтенда"
compose run --rm --build frontend

echo "[4] Запуск контейнеров (кроме backend)"
compose up -d db

echo "[5] Ожидание БД"
# Ждем пока база будет готова. В docker-compose.yml есть healthcheck.
until [ "$(compose ps -q db | xargs docker inspect -f '{{.State.Health.Status}}' 2>/dev/null)" == "healthy" ]; do
    echo "Ожидание готовности базы данных..."
    sleep 2
done

# Загружаем переменные из .env для работы с БД и Rollbar
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

echo "[6] Запускаем остальные сервисы"
compose up -d --build

echo "[7] Миграции и статика"
compose exec -T backend python manage.py migrate --noinput
compose exec -T backend python manage.py collectstatic --noinput

echo "[8] Перезапуск nginx"
if compose config --services | grep -qx "nginx"; then
    NGINX_ID=$(compose ps -q nginx 2>/dev/null || true)
    if [ -n "$NGINX_ID" ]; then
        compose exec -T nginx nginx -s reload
    else
        echo "nginx не запущен, пропускаем перезапуск"
    fi
else
    echo "nginx не определен в compose, пропускаем перезапуск"
fi

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
compose ps
