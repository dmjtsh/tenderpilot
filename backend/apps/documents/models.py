from django.db import models


class TenderDocument(models.Model):
    class ParseStatus(models.TextChoices):
        PENDING = "pending", "Ожидает"
        PROCESSING = "processing", "Обработка"
        DONE = "done", "Готово"
        FAILED = "failed", "Ошибка"
        SKIPPED = "skipped", "Пропущен"
        CLEANED = "cleaned", "Очищен"

    tender = models.ForeignKey(
        "tenders.Tender",
        on_delete=models.CASCADE,
        related_name="documents",
    )
    filename = models.CharField(max_length=500)
    file_type = models.CharField(max_length=20, blank=True)
    s3_key = models.CharField(max_length=1000, unique=True)
    file_size = models.PositiveIntegerField(default=0)

    parent_document = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    archive_path = models.CharField(max_length=1000, blank=True)

    parsed_text = models.TextField(blank=True)
    is_scanned = models.BooleanField(default=False)
    file_hash = models.CharField(max_length=32, blank=True, db_index=True)

    parse_status = models.CharField(
        max_length=12,
        choices=ParseStatus.choices,
        default=ParseStatus.PENDING,
        db_index=True,
    )
    parse_error = models.TextField(blank=True)
    content_priority = models.PositiveSmallIntegerField(default=99)

    created_at = models.DateTimeField(auto_now_add=True)
    parsed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Документ тендера"
        verbose_name_plural = "Документы тендеров"
        ordering = ["content_priority", "filename"]

    def __str__(self) -> str:
        return f"{self.filename} ({self.parse_status})"
