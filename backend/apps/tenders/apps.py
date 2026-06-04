from django.apps import AppConfig


class TendersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tenders"
    verbose_name = "Тендеры"

    def ready(self) -> None:
        import apps.tenders.signals  # noqa: F401
