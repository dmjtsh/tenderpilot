#!/usr/bin/env bash
# TenderPilot — быстрый деплой
# Запуск на сервере: bash deploy.sh
set -euo pipefail

APP="/opt/tenderpilot"
VENV="$APP/venv/bin"
RED='\033[0;31m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'
step() { echo -e "\n${BLUE}▸ $*${NC}"; }
ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
fail() { echo -e "${RED}  ✗ $*${NC}"; exit 1; }

cd "$APP" || fail "Директория $APP не найдена"

step "Git pull"
git pull origin main --ff-only || fail "git pull не удался — возможен конфликт"
COMMIT=$(git log --oneline -1)
ok "$COMMIT"

step "pip install"
$VENV/pip install -q -r backend/requirements.txt 2>/dev/null && ok "зависимости" || ok "requirements.txt не изменился"

step "Миграции"
cd "$APP/backend"
$VENV/python manage.py migrate --no-input 2>&1 | tail -5
ok "миграции"

step "Django static"
$VENV/python manage.py collectstatic --no-input -q 2>/dev/null
ok "collectstatic"

step "Frontend build"
cd "$APP/frontend"
npx next build 2>&1 | tail -3
ok "frontend собран"

step "Рестарт сервисов"
systemctl restart tenderpilot-web
systemctl restart tenderpilot-worker
systemctl restart tenderpilot-beat
systemctl restart tenderpilot-frontend
systemctl reload nginx
ok "web + worker + beat + frontend + nginx"

step "Проверка"
sleep 2
for svc in tenderpilot-web tenderpilot-worker tenderpilot-beat tenderpilot-frontend nginx; do
    if systemctl is-active --quiet "$svc"; then
        ok "$svc"
    else
        fail "$svc не запустился!"
    fi
done

echo -e "\n${GREEN}▸ Деплой завершён: $COMMIT${NC}"
