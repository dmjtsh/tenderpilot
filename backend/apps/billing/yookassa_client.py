import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


def _configure() -> None:
    from yookassa import Configuration
    Configuration.account_id = settings.YOOKASSA_SHOP_ID
    Configuration.secret_key = settings.YOOKASSA_SECRET_KEY


def create_first_payment(
    amount: int,
    plan: str,
    interval: str,
    user_id: int,
    return_url: str,
) -> Any:
    from yookassa import Payment as YooPayment
    _configure()
    return YooPayment.create({
        "amount": {"value": str(amount), "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": return_url},
        "capture": True,
        "description": f"TendeRoll {plan} ({interval})",
        "metadata": {
            "user_id": str(user_id),
            "plan": plan,
            "interval": interval,
        },
    })


def fetch_payment(payment_id: str) -> Any:
    from yookassa import Payment as YooPayment
    _configure()
    return YooPayment.find_one(payment_id)


def create_recurring_payment(
    amount: int,
    payment_method_id: str,
    plan: str,
    interval: str,
    user_id: int,
) -> Any:
    from yookassa import Payment as YooPayment
    _configure()
    return YooPayment.create({
        "amount": {"value": str(amount), "currency": "RUB"},
        "payment_method_id": payment_method_id,
        "capture": True,
        "description": f"TendeRoll {plan} ({interval})",
        "metadata": {
            "user_id": str(user_id),
            "plan": plan,
            "interval": interval,
            "recurring": "true",
        },
    })
