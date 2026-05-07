import math
from datetime import datetime

import yaml
from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from apps.documents.models import TenderDocument
from apps.tenders.models import Experiment, PromptTemplate, Tender
from apps.tenders.services import run_experiment_batch


class Command(BaseCommand):
    help = "Run an A/B experiment from a YAML config file"

    def add_arguments(self, parser) -> None:
        parser.add_argument("--config", type=str, required=True, help="Path to experiment YAML config")
        parser.add_argument("--output", type=str, default="", help="Output report file path")
        parser.add_argument("--count", type=int, default=10, help="Number of tenders (default 10)")
        parser.add_argument("--tender-ids", type=str, default="", help="Comma-separated tender IDs")

    def handle(self, *args, **options) -> None:
        config_path: str = options["config"]
        output_path: str = options["output"]
        count: int = options["count"]
        tender_ids_raw: str = options["tender_ids"]

        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        name = config.get("name", "Unnamed experiment")
        description = config.get("description", "")
        variants = config.get("variants", [])

        if not variants:
            self.stderr.write(self.style.ERROR("No variants defined in config"))
            return

        valid_strategies = {"rag", "full"}
        for v in variants:
            if "label" not in v or "name" not in v:
                self.stderr.write(self.style.ERROR(f"Variant missing 'label' or 'name': {v}"))
                return
            strategy = v.get("strategy", "rag")
            if strategy not in valid_strategies:
                self.stderr.write(self.style.ERROR(f"Invalid strategy '{strategy}' in variant [{v['label']}]"))
                return
            slug = v.get("prompt_template", "summary_v1")
            if not PromptTemplate.objects.filter(name=slug, is_active=True).exists():
                self.stderr.write(self.style.ERROR(f"PromptTemplate '{slug}' not found or inactive"))
                return

        if tender_ids_raw:
            ids = [int(x.strip()) for x in tender_ids_raw.split(",") if x.strip()]
            tender_ids = list(
                Tender.objects.filter(id__in=ids).values_list("id", flat=True)
            )
            missing = set(ids) - set(tender_ids)
            if missing:
                self.stderr.write(self.style.WARNING(f"Tenders not found: {missing}"))
            tender_ids = [tid for tid in ids if tid in set(tender_ids)]
        else:
            tender_ids = self._select_tender_ids(count)

        if not tender_ids:
            self.stderr.write(self.style.ERROR("No tenders with parsed documents found."))
            return

        experiment = Experiment.objects.create(
            name=name,
            description=description,
            tender_ids=tender_ids,
            variants=variants,
        )

        self.stdout.write(
            f"Experiment '{name}' created (id={experiment.id}), "
            f"{len(tender_ids)} tenders, {len(variants)} variants"
        )

        if not output_path:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            slug = name.lower().replace(" ", "_")[:40]
            output_path = f"experiment_{slug}_{ts}.txt"

        run_experiment_batch(
            experiment,
            output_path=output_path,
            stdout=self.stdout,
        )

        self.stdout.write(self.style.SUCCESS(
            f"Done. Experiment '{name}' completed. Report: {output_path}"
        ))

    def _select_tender_ids(self, count: int) -> list[int]:
        qs = (
            Tender.objects
            .annotate(
                done_doc_count=Count(
                    "documents",
                    filter=Q(
                        documents__parse_status=TenderDocument.ParseStatus.DONE,
                        documents__is_scanned=False,
                    ) & ~Q(documents__parsed_text=""),
                )
            )
            .filter(done_doc_count__gte=3)
        )

        n_small = max(1, math.ceil(count * 0.3))
        n_medium = max(1, math.ceil(count * 0.4))
        n_large = count - n_small - n_medium

        small = list(qs.filter(done_doc_count__lte=3).order_by("?").values_list("id", flat=True)[:n_small])
        medium = list(qs.filter(done_doc_count__gte=4, done_doc_count__lte=7).order_by("?").values_list("id", flat=True)[:n_medium])
        large = list(qs.filter(done_doc_count__gte=8).order_by("?").values_list("id", flat=True)[:n_large])

        result = small + medium + large
        if len(result) < count:
            existing = set(result)
            extra = list(qs.exclude(id__in=existing).order_by("?").values_list("id", flat=True)[:count - len(result)])
            result.extend(extra)

        self.stdout.write(f"Buckets: small={len(small)}, medium={len(medium)}, large={len(large)}")
        return result
