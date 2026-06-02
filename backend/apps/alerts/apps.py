from django.apps import AppConfig


class AlertsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.alerts"
    verbose_name = "Алерты"

    def ready(self) -> None:
        from .metrics import register_collector
        register_collector()
