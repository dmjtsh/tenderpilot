import os
from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost", cast=Csv())

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "django_prometheus",
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "drf_spectacular",
    "django_filters",
    "django_celery_beat",
]

LOCAL_APPS = [
    "apps.users",
    "apps.tenders",
    "apps.search",
    "apps.documents",
    "apps.billing",
    "apps.alerts",
    "apps.customers",
    "apps.referrals",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database
_db_url = config("DATABASE_URL")
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _db_url.split("/")[-1],
        "USER": _db_url.split("://")[1].split(":")[0],
        "PASSWORD": _db_url.split(":")[2].split("@")[0],
        "HOST": _db_url.split("@")[1].split(":")[0],
        "PORT": _db_url.split("@")[1].split(":")[1].split("/")[0],
    }
}

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

# CORS
CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="http://localhost:3000", cast=Csv())

# CSRF
CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="https://tenderoll.ru,https://www.tenderoll.ru",
    cast=Csv(),
)

# JWT
from datetime import timedelta
from celery.schedules import crontab
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
}

# Email
EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = config("EMAIL_HOST", default="smtp.yandex.ru")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_USE_SSL = config("EMAIL_USE_SSL", default=False, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@tenderoll.ru")
FRONTEND_BASE_URL = config("FRONTEND_BASE_URL", default="http://localhost:3000")
PASSWORD_RESET_TIMEOUT = 3600

# DRF Spectacular
SPECTACULAR_SETTINGS = {
    "TITLE": "Tenderoll API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# Celery
CELERY_BROKER_URL = config("REDIS_URL", default="redis://localhost:6379")
CELERY_RESULT_BACKEND = config("REDIS_URL", default="redis://localhost:6379")
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_WORKER_SEND_TASK_EVENTS = True
CELERY_TASK_SEND_SENT_EVENT = True

# Пользовательские действия идут в очередь high_priority,
# фоновые задачи — в default очередь celery.
# Воркер запускается с -Q high_priority,celery (порядок = приоритет)
CELERY_TASK_ROUTES = {
    "apps.documents.tasks.download_and_parse_documents": {"queue": "high_priority"},
    "apps.documents.tasks.parse_document": {"queue": "high_priority"},
    "apps.documents.tasks.index_document_chunks": {"queue": "high_priority"},
    "apps.search.tasks.rebuild_direction_vector": {"queue": "high_priority"},
}

CELERY_BEAT_SCHEDULE = {
    "sync-active-tenders": {
        "task": "apps.tenders.tasks.sync_active_tenders",
        "schedule": crontab(minute=0),  # каждый час в :00
    },
"cleanup-old-documents": {
        "task": "apps.documents.tasks.cleanup_old_documents",
        "schedule": crontab(hour=3, minute=0, day_of_week="sunday"),
    },
    "cleanup-doc-chunks": {
        "task": "apps.documents.tasks.cleanup_doc_chunks",
        "schedule": crontab(minute=0),
    },
    "check-pipeline-health": {
        "task": "apps.alerts.tasks.check_pipeline_health",
        "schedule": crontab(minute="*/15"),
    },
    "check-coverage": {
        "task": "apps.alerts.tasks.check_coverage",
        "schedule": crontab(minute=0, hour="*/3"),  # каждые 3 часа
    },
    "cleanup-finished-tenders": {
        "task": "apps.tenders.tasks.cleanup_finished_tenders",
        "schedule": crontab(hour=4, minute=0, day_of_week="sunday"),  # после cleanup-old-documents
    },
    "sync-tenderguru": {
        "task": "apps.tenders.tasks.sync_tenderguru",
        "schedule": crontab(minute=15, hour="*/2"),
    },
    "process-renewals": {
        "task": "apps.billing.tasks.process_renewals",
        "schedule": crontab(hour=3, minute=0),
    },
    "expire-canceled-subscriptions": {
        "task": "apps.billing.tasks.expire_canceled_subscriptions",
        "schedule": crontab(hour=3, minute=30),
    },
}

# Qdrant
QDRANT_URL = config("QDRANT_URL", default="http://localhost:6333")

# MinIO / S3
MINIO_ENDPOINT = config("MINIO_ENDPOINT", default="localhost:9000")
MINIO_ACCESS_KEY = config("MINIO_ACCESS_KEY", default="tender_admin")
MINIO_SECRET_KEY = config("MINIO_SECRET_KEY", default="tender_secret_123")
MINIO_BUCKET_DOCUMENTS = "documents"

# Anthropic
ANTHROPIC_API_KEY = config("ANTHROPIC_API_KEY", default="")

# OpenAI
OPENAI_API_KEY = config("OPENAI_API_KEY", default="")
OPENAI_BASE_URL = config("OPENAI_BASE_URL", default="")

# DeepSeek
DEEPSEEK_API_KEY = config("DEEPSEEK_API_KEY", default="")
DEEPSEEK_BASE_URL = config("DEEPSEEK_BASE_URL", default="https://api.deepseek.com")

# Telegram
TELEGRAM_BOT_TOKEN = config("TELEGRAM_BOT_TOKEN", default="")
TELEGRAM_ADMIN_CHAT_ID = config("TELEGRAM_ADMIN_CHAT_ID", default="")
TELEGRAM_API_ID = config("TELEGRAM_API_ID", default=0, cast=int)
TELEGRAM_API_HASH = config("TELEGRAM_API_HASH", default="")
TELEGRAM_PHONE = config("TELEGRAM_PHONE", default="+573128868945")

# Proxy (для RusProfile)
RUSPROFILE_PROXY_URL = config("RUSPROFILE_PROXY_URL", default="")

# TenderGuru
TENDERGURU_API_KEY = config("TENDERGURU_API_KEY", default="")

# DaData
DADATA_TOKEN = config("DADATA_TOKEN", default="")

# YooKassa
YOOKASSA_SHOP_ID = config("YOOKASSA_SHOP_ID", default="")
YOOKASSA_SECRET_KEY = config("YOOKASSA_SECRET_KEY", default="")
YOOKASSA_RETURN_URL = config("YOOKASSA_RETURN_URL", default="https://tenderoll.ru/plan?payment=success")

PLAN_PRICES = {
    "standard": {"monthly": 2990, "halfyearly": 14950, "yearly": 26910},
    "premium": {"monthly": 6990, "halfyearly": 34950, "yearly": 62910},
}


if DEBUG:
    INSTALLED_APPS += ["django_extensions"]
