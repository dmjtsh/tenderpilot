#!/usr/bin/env bash
# =============================================================================
# TenderPilot — деплой в одну кнопку
# Запуск: bash start.sh
# Требования: Ubuntu 22.04, root или sudo, интернет
# =============================================================================
set -euo pipefail

# ─── Цвета ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERR]${NC}  $*"; exit 1; }
step()    { echo -e "\n${BOLD}━━━ $* ━━━${NC}"; }

# ─── Конфиг ──────────────────────────────────────────────────────────────────
APP_DIR="/opt/tenderpilot"
REPO_URL="${REPO_URL:-}"           # задать снаружи или будет запрошено
DOMAIN="${DOMAIN:-}"               # домен или IP сервера
PYTHON="python3"
VENV_DIR="$APP_DIR/venv"
BACKEND_DIR="$APP_DIR/backend"
LOG_DIR="/var/log/tenderpilot"

# ─── Проверка прав ────────────────────────────────────────────────────────────
step "Проверка окружения"
[[ $EUID -ne 0 ]] && error "Нужен root: sudo bash start.sh"
[[ $(lsb_release -rs 2>/dev/null || echo "0") != "22.04" ]] && \
    warn "Скрипт тестировался на Ubuntu 22.04. Продолжаем..."
success "Права OK"

# ─── Запрашиваем параметры если не заданы ────────────────────────────────────
step "Параметры деплоя"
if [[ -z "$REPO_URL" ]]; then
    read -rp "Git URL репозитория (Enter = пропустить, если код уже в $APP_DIR): " REPO_URL
fi
if [[ -z "$DOMAIN" ]]; then
    read -rp "Домен или IP сервера (напр. 1.2.3.4 или tender.example.com): " DOMAIN
fi
DOMAIN="${DOMAIN:-localhost}"

# ─── 1. Системные пакеты ──────────────────────────────────────────────────────
step "1/8  Системные пакеты"
apt-get update -qq
apt-get install -y -qq \
    curl wget git nginx supervisor \
    python3 python3-venv python3-dev \
    python3-pip build-essential \
    libpq-dev libxml2-dev libxslt1-dev \
    certbot python3-certbot-nginx \
    antiword unrar-free \
    htop ncdu ufw > /dev/null
success "Пакеты установлены"

# ─── 2. Docker ───────────────────────────────────────────────────────────────
step "2/8  Docker"
if ! command -v docker &>/dev/null; then
    info "Устанавливаем Docker..."
    curl -fsSL https://get.docker.com | sh > /dev/null
    systemctl enable --now docker
    success "Docker установлен"
else
    success "Docker уже есть: $(docker --version)"
fi

if ! command -v docker compose &>/dev/null 2>&1; then
    apt-get install -y -qq docker-compose-plugin > /dev/null
fi
success "Docker Compose: $(docker compose version --short)"

# ─── 3. Код ──────────────────────────────────────────────────────────────────
step "3/8  Код приложения"
if [[ -n "$REPO_URL" ]]; then
    if [[ -d "$APP_DIR/.git" ]]; then
        info "Обновляем репозиторий..."
        git -C "$APP_DIR" pull --ff-only
    else
        info "Клонируем $REPO_URL → $APP_DIR"
        git clone "$REPO_URL" "$APP_DIR"
    fi
elif [[ ! -d "$APP_DIR" ]]; then
    error "Репозиторий не указан и $APP_DIR не существует. Задай REPO_URL."
else
    info "Используем существующий код в $APP_DIR"
fi
success "Код готов в $APP_DIR"


# ─── 4. .env ─────────────────────────────────────────────────────────────────
step "4/8  Проверка .env"
ENV_FILE="$BACKEND_DIR/.env"
[[ ! -f "$ENV_FILE" ]] && error ".env не найден: $ENV_FILE — создай его перед запуском скрипта"
success ".env найден"


# ─── 5. Python venv + зависимости ────────────────────────────────────────────
step "5/8  Python зависимости"
if [[ ! -d "$VENV_DIR" ]]; then
    info "Создаём virtualenv..."
    $PYTHON -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

info "Устанавливаем requirements..."
pip install --quiet --upgrade pip
pip install --quiet -r "$BACKEND_DIR/requirements/base.txt"
success "Python зависимости установлены"

# ─── 6. Docker Compose сервисы (Postgres, Redis, Qdrant, MinIO) ──────────────
step "6/8  Запуск инфраструктуры (Docker)"
cd "$APP_DIR"
docker compose up -d --remove-orphans

info "Ждём готовности PostgreSQL..."
for i in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U tender_user -d tenders &>/dev/null; then
        success "PostgreSQL готов"
        break
    fi
    [[ $i -eq 30 ]] && error "PostgreSQL не поднялся за 30 сек"
    sleep 1
done

info "Ждём готовности Redis..."
for i in $(seq 1 15); do
    if docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
        success "Redis готов"
        break
    fi
    sleep 1
done

# ─── 7. Миграции + начальная загрузка ────────────────────────────────────────
step "7/8  Миграции Django"
cd "$BACKEND_DIR"
source "$VENV_DIR/bin/activate"

python manage.py migrate --run-syncdb
success "Миграции выполнены"

# Создаём суперпользователя если нужно
if ! python manage.py shell -c "from django.contrib.auth import get_user_model; \
        exit(0 if get_user_model().objects.filter(is_superuser=True).exists() else 1)" 2>/dev/null; then
    warn "Суперпользователь не найден. Создаём..."
    DJANGO_SUPERUSER_EMAIL="admin@tenderpilot.ru" \
    DJANGO_SUPERUSER_PASSWORD="ChangeMe123!" \
    python manage.py createsuperuser \
        --username admin --email admin@tenderpilot.ru --noinput 2>/dev/null || true
    warn "Логин: admin / ChangeMe123! — смени пароль после входа!"
fi

python manage.py collectstatic --noinput --clear > /dev/null 2>&1 || true

# ─── 8. Systemd сервисы ───────────────────────────────────────────────────────
step "8/8  Systemd сервисы"
mkdir -p "$LOG_DIR"

# ── Gunicorn ──
cat > /etc/systemd/system/tenderpilot-web.service << EOF
[Unit]
Description=TenderPilot Django API (Gunicorn)
After=network.target docker.service
Requires=docker.service

[Service]
User=root
WorkingDirectory=$BACKEND_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV_DIR/bin/gunicorn config.wsgi:application \
    --workers 3 \
    --worker-class gthread \
    --threads 2 \
    --bind 127.0.0.1:8000 \
    --timeout 120 \
    --access-logfile $LOG_DIR/gunicorn-access.log \
    --error-logfile $LOG_DIR/gunicorn-error.log
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# ── Celery Worker ──
cat > /etc/systemd/system/tenderpilot-worker.service << EOF
[Unit]
Description=TenderPilot Celery Worker
After=network.target docker.service tenderpilot-web.service
Requires=docker.service

[Service]
User=root
WorkingDirectory=$BACKEND_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV_DIR/bin/celery -A config worker \
    --loglevel=info \
    --concurrency=1 \
    --logfile=$LOG_DIR/celery-worker.log
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# ── Celery Beat ──
cat > /etc/systemd/system/tenderpilot-beat.service << EOF
[Unit]
Description=TenderPilot Celery Beat (Scheduler)
After=network.target docker.service tenderpilot-worker.service
Requires=docker.service

[Service]
User=root
WorkingDirectory=$BACKEND_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV_DIR/bin/celery -A config beat \
    --loglevel=info \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler \
    --logfile=$LOG_DIR/celery-beat.log
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable tenderpilot-web tenderpilot-worker tenderpilot-beat
systemctl restart tenderpilot-web tenderpilot-worker tenderpilot-beat
success "Systemd сервисы запущены"

# ─── Nginx ───────────────────────────────────────────────────────────────────
step "Nginx"

SSL_CERT="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
HAS_SSL=false
[[ -f "$SSL_CERT" ]] && HAS_SSL=true

# Определяем — это реальный домен или IP (для certbot нужен домен)
IS_DOMAIN=false
if [[ "$DOMAIN" =~ ^[a-zA-Z] ]]; then IS_DOMAIN=true; fi

if $HAS_SSL; then
    # SSL уже есть — пишем конфиг с редиректом http→https
    cat > /etc/nginx/sites-available/tenderpilot << EOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl;
    server_name $DOMAIN www.$DOMAIN;

    ssl_certificate     /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    include             /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam         /etc/letsencrypt/ssl-dhparams.pem;

    client_max_body_size 50M;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }

    location /admin/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /static/ {
        alias $BACKEND_DIR/staticfiles/;
        expires 30d;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF
    success "Nginx настроен с SSL"
else
    # SSL нет — plain HTTP
    cat > /etc/nginx/sites-available/tenderpilot << EOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    client_max_body_size 50M;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }

    location /admin/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /static/ {
        alias $BACKEND_DIR/staticfiles/;
        expires 30d;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF

    ln -sf /etc/nginx/sites-available/tenderpilot /etc/nginx/sites-enabled/tenderpilot
    rm -f /etc/nginx/sites-enabled/default
    nginx -t && systemctl restart nginx
    success "Nginx настроен (HTTP)"

    # Автоматически получаем SSL если это домен и certbot доступен
    if $IS_DOMAIN && command -v certbot &>/dev/null; then
        info "Пробуем получить SSL сертификат для $DOMAIN..."
        if certbot --nginx --non-interactive --agree-tos --register-unsafely-without-email \
            -d "$DOMAIN" -d "www.$DOMAIN" 2>/dev/null; then
            HAS_SSL=true
            success "SSL сертификат получен!"
        else
            warn "Не удалось получить SSL (DNS ещё не прокинулся?). Продолжаем с HTTP."
            warn "После прокидывания DNS запусти: certbot --nginx -d $DOMAIN -d www.$DOMAIN"
        fi
    fi
fi

ln -sf /etc/nginx/sites-available/tenderpilot /etc/nginx/sites-enabled/tenderpilot
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# ─── Файрвол ─────────────────────────────────────────────────────────────────
ufw allow OpenSSH > /dev/null
ufw allow 'Nginx Full' > /dev/null
ufw --force enable > /dev/null
success "Файрвол настроен (SSH + HTTP/HTTPS открыты)"


# ─── Фронтенд (Next.js) ───────────────────────────────────────────────────────
step "Фронтенд (Next.js)"
FRONTEND_DIR="$APP_DIR/frontend"

# Ставим Node.js если нет
if ! command -v node &>/dev/null; then
    info "Устанавливаем Node.js 20..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - > /dev/null
    apt-get install -y -qq nodejs > /dev/null
    success "Node.js $(node -v) установлен"
else
    success "Node.js уже есть: $(node -v)"
fi

# .env.local для фронта (https если SSL есть, иначе http)
if $HAS_SSL; then
    FRONTEND_API_URL="https://$DOMAIN/api/v1"
else
    FRONTEND_API_URL="http://$DOMAIN/api/v1"
fi
echo "NEXT_PUBLIC_API_URL=$FRONTEND_API_URL" > "$FRONTEND_DIR/.env.local"
success ".env.local создан → NEXT_PUBLIC_API_URL=$FRONTEND_API_URL"

# Зависимости и сборка
info "npm install..."
cd "$FRONTEND_DIR" && npm install --silent

info "npm run build..."
npm run build

# Systemd сервис
cat > /etc/systemd/system/tenderpilot-frontend.service << SVCEOF
[Unit]
Description=TenderPilot Next.js Frontend
After=network.target

[Service]
User=root
WorkingDirectory=$FRONTEND_DIR
ExecStart=/usr/bin/node node_modules/.bin/next start -p 3000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable tenderpilot-frontend
systemctl restart tenderpilot-frontend
success "Фронтенд запущен на порту 3000"

# ─── Итог ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  TenderPilot задеплоен успешно! 🎉     ${NC}"
echo -e "${GREEN}${BOLD}════════════════════════════════════════${NC}"
echo ""
echo -e "  API:      ${BOLD}http://$DOMAIN/api/v1/${NC}"
echo -e "  Admin:    ${BOLD}http://$DOMAIN/admin/${NC}  (admin / ChangeMe123!)"
echo ""
echo -e "  Логи:"
echo -e "    journalctl -u tenderpilot-web -f"
echo -e "    journalctl -u tenderpilot-worker -f"
echo -e "    journalctl -u tenderpilot-beat -f"
echo ""
echo -e "  Статус сервисов:"
echo -e "    systemctl status tenderpilot-web tenderpilot-worker tenderpilot-beat"
echo ""
echo -e "  Синхронизация тендеров — каждый час автоматически."
echo -e "  Запустить вручную:"
echo -e "    cd $BACKEND_DIR && source $VENV_DIR/bin/activate"
echo -e "    celery -A config call apps.tenders.tasks.sync_active_tenders"
echo ""
