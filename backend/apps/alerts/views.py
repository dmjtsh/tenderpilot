import json
import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

COMMANDS = {
    "/coverage": "check_coverage",
    "/покрытие": "check_coverage",
}


@csrf_exempt
@require_POST
def telegram_webhook(request, token: str):
    if token != settings.TELEGRAM_BOT_TOKEN:
        return HttpResponseForbidden()

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    message = data.get("message") or data.get("edited_message")
    if not message:
        return HttpResponse("ok")

    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip().lower().split("@")[0]

    if not text.startswith("/"):
        return HttpResponse("ok")

    command = text.split()[0]

    if command in COMMANDS:
        from .tasks import check_coverage
        from .telegram import send_telegram

        send_telegram("⏳ Запрашиваю данные у ЕИС...", )
        check_coverage.delay(notify_always=True)
    else:
        from .telegram import send_telegram
        cmds = "\n".join(f"  {k}" for k in COMMANDS)
        send_telegram(f"Неизвестная команда. Доступные:\n{cmds}")

    return HttpResponse("ok")
