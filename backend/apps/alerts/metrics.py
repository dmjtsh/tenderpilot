from prometheus_client import REGISTRY
from prometheus_client.core import GaugeMetricFamily


class TenderPipelineCollector:
    """Custom Prometheus collector — reads DB on each scrape."""

    def collect(self):
        # Import здесь, чтобы не ломать старт при cold import до migrate
        from django.db import connection

        yield from self._tender_counts()
        yield from self._pipeline_runs()
        yield from self._document_stats()
        yield from self._data_quality()

    def _tender_counts(self):
        from apps.tenders.models import Tender
        from django.db.models import Count

        rows = (
            Tender.objects.values("source", "status")
            .annotate(cnt=Count("id"))
            .order_by()
        )

        g = GaugeMetricFamily(
            "tenderpilot_tenders_total",
            "Number of tenders by source and status",
            labels=["source", "status"],
        )
        for row in rows:
            g.add_metric([row["source"], row["status"]], row["cnt"])
        yield g

    def _pipeline_runs(self):
        from apps.alerts.models import PipelineRun

        last_ts = GaugeMetricFamily(
            "tenderpilot_pipeline_last_success_timestamp_seconds",
            "Unix timestamp of the last OK/PARTIAL pipeline run",
            labels=["task_name"],
        )
        last_dur = GaugeMetricFamily(
            "tenderpilot_pipeline_last_duration_ms",
            "Duration in ms of the last pipeline run",
            labels=["task_name"],
        )
        last_errors = GaugeMetricFamily(
            "tenderpilot_pipeline_errors_last_run",
            "Error count from stats JSON of the last pipeline run",
            labels=["task_name"],
        )

        for task in PipelineRun.TaskName.values:
            run = (
                PipelineRun.objects.filter(
                    task_name=task,
                    status__in=[PipelineRun.Status.OK, PipelineRun.Status.PARTIAL],
                )
                .order_by("-finished_at")
                .first()
            )
            if run:
                last_ts.add_metric([task], run.finished_at.timestamp())
                last_dur.add_metric([task], run.duration_ms)
                last_errors.add_metric([task], run.stats.get("errors", 0))

        yield last_ts
        yield last_dur
        yield last_errors

    def _document_stats(self):
        from apps.documents.models import TenderDocument
        from django.db.models import Count

        rows = (
            TenderDocument.objects.values("parse_status")
            .annotate(cnt=Count("id"))
            .order_by()
        )
        g = GaugeMetricFamily(
            "tenderpilot_documents_total",
            "Number of tender documents by parse status",
            labels=["parse_status"],
        )
        for row in rows:
            g.add_metric([row["parse_status"]], row["cnt"])
        yield g

    def _data_quality(self):
        from apps.tenders.models import Tender

        unenriched = Tender.objects.filter(
            status=Tender.Status.ACTIVE, enriched_at__isnull=True
        ).count()
        unembedded = Tender.objects.filter(
            status=Tender.Status.ACTIVE, embedding_id__isnull=True
        ).count()

        g_unenriched = GaugeMetricFamily(
            "tenderpilot_unenriched_tenders_total",
            "Active tenders without enrichment",
        )
        g_unenriched.add_metric([], unenriched)
        yield g_unenriched

        g_unembedded = GaugeMetricFamily(
            "tenderpilot_unembedded_tenders_total",
            "Active tenders without vector embedding",
        )
        g_unembedded.add_metric([], unembedded)
        yield g_unembedded


def register_collector() -> None:
    collector = TenderPipelineCollector()
    REGISTRY.register(collector)
