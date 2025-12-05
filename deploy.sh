#!/bin/bash
set -e

echo "=== Начало деплоя ==="
echo "Обновляю код репозитория..."
git pull

echo "Активирую виртуальное окружение Python..."
source venv/bin/activate

echo "Устанавливаю Python-библиотеки из requirements.txt..."
pip install -r requirements.txt

echo "Устанавливаю/обновляю Node.js библиотеки..."
npm ci --dev

echo "Пересобираю JS-код (фронтенд)..."
./node_modules/.bin/parcel build bundles-src/index.js --dist-dir bundles --public-url="./"

echo "Пересобираю статику Django..."
python manage.py collectstatic --noinput

echo "Применяю миграции базы данных..."
python manage.py migrate

echo "Перезапускаю сервисы Systemd..."
sudo systemctl daemon-reload
sudo systemctl reload postgresql
sudo systemctl reload django
sudo systemctl reload nginx

echo "Предупреждаем Rollbar о деплое."
export $(grep -v '^#' .env | xargs)

REVISION=$(git rev-parse HEAD)
USERNAME=$(whoami)

curl -H "X-Rollbar-Access-Token: $ROLLBAR_ACCESS_TOKEN" \
-X POST 'https://api.rollbar.com/api/1/deploy' \
-d environment=$ROLLBAR_ENVIRONMENT \
-d revision=$REVISION \
-d local_username=$USERNAME

echo "=== Деплой успешно завершен! ==="
echo "Сайт готов к работе."
