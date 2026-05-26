#!/usr/bin/env bash
# TenderPilot — быстрый деплой
# Запуск: bash deploy.sh (или source deploy.sh)

APP="/opt/tenderpilot"
VENV="$APP/venv/bin"
RED='\033[0;31m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'
step() { echo -e "\n${BLUE}▸ $*${NC}"; }
ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
fail() { echo -e "${RED}  ✗ $*${NC}"; return 1 2>/dev/null || exit 1; }

cd "$APP" || { fail "Директория $APP не найдена"; return 1 2>/dev/null || exit 1; }

step "Git pull"
git pull origin main --ff-only || { fail "git pull не удался"; return 1 2>/dev/null || exit 1; }
COMMIT=$(git log --oneline -1)
ok "$COMMIT"

step "pip install"
$VENV/pip install -q -r backend/requirements/base.txt 2>/dev/null
ok "зависимости"

step "Миграции"
cd "$APP/backend"
$VENV/python manage.py migrate --no-input 2>&1 | tail -5
ok "миграции"

step "Django static"
$VENV/python manage.py collectstatic --no-input -v 0 2>&1 || true
ok "collectstatic"

step "Frontend build"
cd "$APP/frontend"
npx next build 2>&1 | tail -3
ok "frontend собран"

step "Обновление systemd сервисов"
cp "$APP/infra/tenderpilot-worker.service" /etc/systemd/system/tenderpilot-worker.service
systemctl daemon-reload
ok "systemd обновлён"

step "Рестарт сервисов"
systemctl restart tenderpilot-web tenderpilot-worker tenderpilot-beat tenderpilot-frontend
systemctl reload nginx
ok "web + worker + beat + frontend + nginx"

step "Проверка"
sleep 2
for svc in tenderpilot-web tenderpilot-worker tenderpilot-beat tenderpilot-frontend nginx; do
    if systemctl is-active --quiet "$svc"; then
        ok "$svc"
    else
        echo -e "${RED}  ✗ $svc не запустился${NC}"
    fi
done

echo -e "\n${GREEN}▸ Деплой завершён: $COMMIT${NC}"
