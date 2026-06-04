import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex


class Customer(models.Model):
    inn = models.CharField(max_length=12, blank=True, db_index=True)
    name = models.CharField(max_length=500)
    full_name = models.CharField(max_length=1000, blank=True)
    region = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Заказчик"
        verbose_name_plural = "Заказчики"
        # INN уникален только когда непустой (частичный индекс Postgres)
        constraints = [
            models.UniqueConstraint(
                fields=["inn"],
                condition=~Q(inn=""),
                name="unique_non_empty_inn",
            )
        ]

    def __str__(self) -> str:
        return self.name


class Tender(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Активный"
        FINISHED = "finished", "Завершён"
        CANCELLED = "cancelled", "Отменён"

    class Source(models.TextChoices):
        EIS = "eis", "ЕИС (zakupki.gov.ru)"
        BIDZAAR = "bidzaar", "Bidzaar"
        KOMTENDER = "komtender", "Komtender"
        TENDERGURU = "tenderguru", "TenderGuru"
        OTHER = "other", "Другой источник"

    class LawType(models.TextChoices):
        FZ44 = "44-ФЗ", "44-ФЗ"
        FZ223 = "223-ФЗ", "223-ФЗ"
        PP615 = "615-ПП", "615-ПП"
        COMMERCIAL = "b2b", "Коммерческая закупка"

    class ProcedureType(models.TextChoices):
        AUCTION = "auction", "Электронный аукцион"
        CONTEST = "contest", "Конкурс"
        REQUEST_QUOTATIONS = "request_quotations", "Запрос котировок"
        REQUEST_PROPOSALS = "request_proposals", "Запрос предложений"
        SINGLE_SOURCE = "single_source", "Единственный поставщик"
        OTHER = "other", "Иной"

    class DocsDownloadStatus(models.TextChoices):
        IDLE = "", "Не начато"
        DOWNLOADING = "downloading", "Загрузка"
        DONE = "done", "Готово"
        NO_DOCS = "no_docs", "Нет документов"
        FAILED = "failed", "Ошибка"

    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.EIS,
        db_index=True,
    )
    number = models.CharField(max_length=50, db_index=True)
    title = models.TextField()
    nmck = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tenders",
    )
    region = models.CharField(max_length=100, blank=True)
    okpd_codes = models.JSONField(default=list)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deadline_at = models.DateTimeField(null=True, blank=True)
    auction_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    law_type = models.CharField(max_length=10, choices=LawType.choices, blank=True, db_index=True)
    procedure_type = models.CharField(
        max_length=25, choices=ProcedureType.choices, default=ProcedureType.OTHER, db_index=True
    )
    trading_platform = models.CharField(max_length=500, blank=True)
    trading_platform_url = models.URLField(max_length=500, blank=True)
    bid_security_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    bid_security_required = models.BooleanField(null=True, blank=True)
    contract_security_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    contract_security_percent = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    source_url = models.URLField(max_length=1000, blank=True)
    raw_json = models.JSONField(default=dict)
    ai_summary = models.TextField(blank=True)
    embedding_id = models.UUIDField(null=True, blank=True)
    docs_indexed_at = models.DateTimeField(null=True, blank=True)
    enriched_at = models.DateTimeField(null=True, blank=True)
    content_quality = models.SmallIntegerField(default=0, db_index=True)
    docs_download_status = models.CharField(
        max_length=20,
        choices=DocsDownloadStatus.choices,
        default=DocsDownloadStatus.IDLE,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    search_vector = SearchVectorField(null=True, blank=True)

    class Meta:
        verbose_name = "Тендер"
        verbose_name_plural = "Тендеры"
        ordering = ["-published_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["number", "source"],
                name="unique_number_per_source",
            )
        ]
        indexes = [
            GinIndex(fields=["search_vector"], name="tender_search_vector_gin"),
        ]

    def __str__(self) -> str:
        return f"{self.number}: {self.title[:80]}"


class TenderPipeline(models.Model):
    class PipelineStatus(models.TextChoices):
        NEW = "new", "Новый"
        STUDYING = "studying", "Изучаю"
        PREPARING = "preparing", "Готовлю заявку"
        SUBMITTED = "submitted", "Подал"
        WON = "won", "Выиграл"
        LOST = "lost", "Проиграл"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pipeline_entries"
    )
    tender = models.ForeignKey(
        Tender, on_delete=models.CASCADE, related_name="pipeline_entries"
    )
    profile = models.ForeignKey(
        "users.CompanyProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pipeline_entries",
    )
    status = models.CharField(max_length=20, choices=PipelineStatus.choices)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "tender")
        verbose_name = "Pipeline-запись"
        verbose_name_plural = "Pipeline-записи"

    def __str__(self) -> str:
        return f"{self.user} → {self.tender.number} [{self.status}]"


class PipelineComment(models.Model):
    pipeline_entry = models.ForeignKey(
        TenderPipeline, on_delete=models.CASCADE, related_name="comments"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pipeline_comments"
    )
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Comment by {self.user} on pipeline #{self.pipeline_entry_id}"


class PipelineActivity(models.Model):
    class ActionType(models.TextChoices):
        CREATED = "created", "Создано"
        STATUS_CHANGED = "status_changed", "Статус изменён"
        COMMENT_ADDED = "comment_added", "Комментарий"

    pipeline_entry = models.ForeignKey(
        TenderPipeline, on_delete=models.CASCADE, related_name="activities"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pipeline_activities"
    )
    action_type = models.CharField(max_length=30, choices=ActionType.choices)
    old_value = models.CharField(max_length=100, blank=True)
    new_value = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action_type} on pipeline #{self.pipeline_entry_id}"


class PromptTemplate(models.Model):
    name = models.CharField(max_length=50)
    version = models.PositiveIntegerField(default=1)
    system_prompt = models.TextField(blank=True)
    user_template = models.TextField()
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("name", "version")
        ordering = ["name", "-version"]

    def __str__(self) -> str:
        return f"{self.name} v{self.version}"


class Experiment(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        RUNNING = "running", "Выполняется"
        COMPLETED = "completed", "Завершён"

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    tender_ids = models.JSONField(default=list)
    variants = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} [{self.status}]"


class SummaryExperiment(models.Model):
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE, related_name="summary_experiments")
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE, null=True, blank=True, related_name="runs")
    variant_label = models.CharField(max_length=5, blank=True)
    variant_name = models.CharField(max_length=100, blank=True)
    strategy = models.CharField(max_length=30)
    model = models.CharField(max_length=50, default="gpt-4o-mini")
    actual_model = models.CharField(max_length=50, blank=True, default="")
    prompt_template = models.ForeignKey(PromptTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    params = models.JSONField(default=dict)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=8, decimal_places=6, default=0)
    duration_ms = models.PositiveIntegerField(default=0)
    was_truncated = models.BooleanField(default=False)
    truncated_reason = models.CharField(max_length=50, blank=True)
    original_total_tokens = models.PositiveIntegerField(default=0)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        label = f"[{self.variant_label}] " if self.variant_label else ""
        return f"{self.tender.number} {label}[{self.strategy}] {self.created_at:%Y-%m-%d %H:%M}"


class TenderSummaryV2(models.Model):
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE, related_name="summaries_v2")
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="summaries_v2", null=True)
    summary = models.JSONField(default=dict)
    step_metrics = models.JSONField(default=dict)
    total_input_tokens = models.PositiveIntegerField(default=0)
    total_output_tokens = models.PositiveIntegerField(default=0)
    total_cost_usd = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    generation_time_ms = models.PositiveIntegerField(default=0)
    model = models.CharField(max_length=50, default="deepseek-chat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        unique_together = [("tender", "user")]

    def __str__(self) -> str:
        return f"SummaryV2 #{self.tender_id} u={self.user_id} ({self.generation_time_ms}ms, ${self.total_cost_usd})"
