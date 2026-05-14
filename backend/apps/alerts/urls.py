from django.urls import path
from .views import telegram_webhook

urlpatterns = [
    path("tg/<str:token>/", telegram_webhook, name="telegram-webhook"),
]
