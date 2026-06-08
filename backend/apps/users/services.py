from __future__ import annotations

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .models import User


def send_password_reset_email(email: str) -> None:
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    reset_url = f"{settings.FRONTEND_BASE_URL}/reset-password?uid={uid}&token={token}"

    import logging
    logger = logging.getLogger(__name__)
    try:
        send_mail(
            subject="Сброс пароля: TendeRoll",
            message=(
                f"Здравствуйте!\n\n"
                f"Для сброса пароля перейдите по ссылке:\n{reset_url}\n\n"
                f"Ссылка действительна 1 час.\n\n"
                f"Если вы не запрашивали сброс пароля, просто проигнорируйте это письмо."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
        )
    except Exception:
        logger.exception("Failed to send password reset email to %s", user.email)


def confirm_password_reset(uid: str, token: str, new_password: str) -> None:
    try:
        pk = force_str(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=pk)
    except (User.DoesNotExist, ValueError, OverflowError, TypeError):
        raise ValidationError("Недействительная или устаревшая ссылка.")

    if not default_token_generator.check_token(user, token):
        raise ValidationError("Недействительная или устаревшая ссылка.")

    validate_password(new_password, user)
    user.set_password(new_password)
    user.save()
