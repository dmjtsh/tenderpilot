from django.db import models


class PipelineRun(models.Model):
    class TaskName(models.TextChoices):
        SYNC_ACTIVE = "sync_active_tenders"
        ENRICH_TENDER = "enrich_tender"
        EMBED_TENDER = "embed_tender"
        CLEANUP_CHUNKS = "cleanup_doc_chunks"
        CLEANUP_DOCS = "cleanup_old_documents"
        RECOVER = "recover_failed_tenders"

    class Status(models.TextChoices):
        OK = "ok"
        PARTIAL = "partial"
        FAILED = "failed"

    task_name = models.CharField(max_length=50, choices=TaskName.choices, db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(auto_now_add=True)
    duration_ms = models.PositiveIntegerField(default=0)
    stats = models.JSONField(default=dict)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-finished_at"]
        indexes = [models.Index(fields=["task_name", "finished_at"])]

    def __str__(self) -> str:
        return f"{self.task_name} [{self.status}] {self.finished_at:%Y-%m-%d %H:%M}"
