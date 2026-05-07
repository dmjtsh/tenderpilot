import json
import math
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from tqdm import tqdm

from apps.documents.models import TenderDocument
from apps.tenders.models import SummaryExperiment, Tender
from apps.tenders.services import generate_experiment_summary


class Command(BaseCommand):
    help = "Batch A/B test AI summary strategies (RAG vs Full)"

    def add_arguments(self, parser) -> None:
        parser.add_argument("--count", type=int, default=10, help="Number of tenders to test (default 10)")
        parser.add_argument("--output", type=str, default="experiments.txt", help="Output file path")
        parser.add_argument("--tender-ids", type=str, default="", help="Comma-separated tender IDs")
        parser.add_argument("--strategies", type=str, default="rag,full", help="Strategies to test (default rag,full)")

    def handle(self, *args, **options) -> None:
        count: int = options["count"]
        output_path: str = options["output"]
        tender_ids_raw: str = options["tender_ids"]
        strategies_raw: str = options["strategies"]

        strategies = [s.strip() for s in strategies_raw.split(",") if s.strip()]
        valid = {"rag", "full"}
        for s in strategies:
            if s not in valid:
                self.stderr.write(self.style.ERROR(f"Unknown strategy: {s}. Use 'rag' or 'full'."))
                return

        if tender_ids_raw:
            ids = [int(x.strip()) for x in tender_ids_raw.split(",") if x.strip()]
            tenders = list(Tender.objects.select_related("customer").filter(id__in=ids))
            missing = set(ids) - {t.id for t in tenders}
            if missing:
                self.stderr.write(self.style.WARNING(f"Tenders not found: {missing}"))
            tenders.sort(key=lambda t: ids.index(t.id))
        else:
            tenders = self._select_tenders(count)

        if not tenders:
            self.stderr.write(self.style.ERROR("No tenders with parsed documents found."))
            return

        self.stdout.write(f"Selected {len(tenders)} tenders, strategies: {', '.join(strategies)}")

        model_name = "gpt-4o-mini"
        stats: dict[str, list[dict]] = {s: [] for s in strategies}
        errors = 0

        with open(output_path, "w", encoding="utf-8") as f:
            now = datetime.now()
            self._write_header(f, len(tenders), strategies, model_name, now)

            for tender in tqdm(tenders, desc="Experiments"):
                docs = list(
                    TenderDocument.objects.filter(
                        tender=tender,
                        parse_status=TenderDocument.ParseStatus.DONE,
                        is_scanned=False,
                    )
                    .exclude(parsed_text="")
                    .order_by("content_priority", "filename")
                )

                self._write_tender_header(f, tender, docs)

                for strategy in strategies:
                    f.write(f"\n{'─' * 64}\n")
                    f.write(f"СТРАТЕГИЯ: {strategy.upper()}\n")
                    f.write(f"{'─' * 64}\n")

                    try:
                        result = generate_experiment_summary(tender, strategy=strategy)
                        metrics = result["metrics"]
                        summary = result["summary"]

                        SummaryExperiment.objects.create(
                            tender=tender,
                            strategy=metrics["strategy"],
                            model=metrics["model"],
                            input_tokens=metrics["input_tokens"],
                            output_tokens=metrics["output_tokens"],
                            cost_usd=metrics["cost_usd"],
                            duration_ms=metrics["duration_ms"],
                            was_truncated=metrics["was_truncated"],
                            truncated_reason=metrics["truncated_reason"],
                            original_total_tokens=metrics["original_total_tokens"],
                            result=summary,
                        )

                        stats[strategy].append(metrics)
                        self._write_metrics(f, metrics)
                        f.write("\nРезультат:\n")
                        f.write(json.dumps(summary, indent=2, ensure_ascii=False))
                        f.write("\n")

                    except Exception as exc:
                        errors += 1
                        f.write(f"\nОШИБКА: {exc}\n")
                        self.stderr.write(self.style.ERROR(
                            f"  Error {tender.number} [{strategy}]: {exc}"
                        ))

                f.write("\n")
                f.flush()

            self._write_summary(f, stats, errors)

        self.stdout.write(self.style.SUCCESS(f"Done. Results saved to {output_path}"))

    def _select_tenders(self, count: int) -> list[Tender]:
        qs = (
            Tender.objects
            .select_related("customer")
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

        small_qs = qs.filter(done_doc_count__lte=3).order_by("?")
        medium_qs = qs.filter(done_doc_count__gte=4, done_doc_count__lte=7).order_by("?")
        large_qs = qs.filter(done_doc_count__gte=8).order_by("?")

        n_small = max(1, math.ceil(count * 0.3))
        n_medium = max(1, math.ceil(count * 0.4))
        n_large = count - n_small - n_medium

        small = list(small_qs[:n_small])
        medium = list(medium_qs[:n_medium])
        large = list(large_qs[:n_large])

        result = small + medium + large

        if len(result) < count:
            existing_ids = {t.id for t in result}
            extra = list(qs.exclude(id__in=existing_ids).order_by("?")[: count - len(result)])
            result.extend(extra)

        self.stdout.write(
            f"Buckets: small={len(small)}, medium={len(medium)}, large={len(large)}"
        )
        return result

    def _write_header(
        self, f, count: int, strategies: list[str], model: str, now: datetime,
    ) -> None:
        f.write(f"{'=' * 64}\n")
        f.write(f"A/B ТЕСТ AI-РЕЗЮМЕ — {now.strftime('%d %B %Y, %H:%M').lstrip('0')}\n")
        f.write(f"{'=' * 64}\n")
        f.write(f"Всего тендеров: {count}\n")
        f.write(f"Стратегии: {', '.join(strategies)}\n")
        f.write(f"Модель: {model}\n\n")

    def _write_tender_header(self, f, tender: Tender, docs: list[TenderDocument]) -> None:
        f.write(f"{'=' * 64}\n")
        f.write(f"ТЕНДЕР #{tender.id} — {tender.title}\n")
        f.write(f"{'=' * 64}\n")
        f.write(f"Номер: {tender.number}\n")
        f.write(f"URL: {tender.source_url}\n")
        if tender.customer:
            f.write(f"Заказчик: {tender.customer.full_name or tender.customer.name}\n")
        f.write(f"Регион: {tender.region or '—'}\n")
        if tender.nmck:
            f.write(f"НМЦ: {tender.nmck:,.0f} ₽\n".replace(",", " "))
        else:
            f.write("НМЦ: не указана\n")
        f.write(f"Закон: {tender.law_type or '—'}\n")
        if tender.deadline_at:
            f.write(f"Дедлайн подачи: {tender.deadline_at.strftime('%d %B %Y')}\n")

        f.write(f"\nДокументы тендера:\n")
        total_chars = 0
        for d in docs:
            chars = len(d.parsed_text) if d.parsed_text else 0
            total_chars += chars
            f.write(f"  - {d.filename} (priority={d.content_priority}, {chars:,} символов)\n".replace(",", " "))
        f.write(f"Всего символов: {total_chars:,}\n".replace(",", " "))

    def _write_metrics(self, f, metrics: dict) -> None:
        f.write("Метрики:\n")
        f.write(f"  Входных токенов: {metrics['input_tokens']:,}\n".replace(",", " "))
        f.write(f"  Выходных токенов: {metrics['output_tokens']:,}\n".replace(",", " "))
        f.write(f"  Стоимость: ${float(metrics['cost_usd']):.4f}\n")
        f.write(f"  Время: {metrics['duration_ms'] / 1000:.1f} сек\n")
        if metrics.get("was_truncated"):
            f.write(f"  Усечение: ДА, {metrics['truncated_reason']}\n")
        else:
            f.write("  Усечение: нет\n")

    def _write_summary(self, f, stats: dict[str, list[dict]], errors: int) -> None:
        f.write(f"\n{'=' * 64}\n")
        f.write("СВОДКА\n")
        f.write(f"{'=' * 64}\n")

        total_experiments = sum(len(v) for v in stats.values())
        strategy_counts = ", ".join(f"{len(v)} {k}" for k, v in stats.items() if v)
        f.write(f"Всего экспериментов: {total_experiments} ({strategy_counts})\n")
        if errors:
            f.write(f"Ошибок: {errors}\n")

        full_stats = stats.get("full", [])
        if full_stats:
            truncated = sum(1 for m in full_stats if m.get("was_truncated"))
            f.write(f"Усечений в Full: {truncated} из {len(full_stats)}\n")

        f.write("\nСредние метрики:\n")

        headers = [""]
        for s in stats:
            if stats[s]:
                headers.append(s.upper())
        col_w = 16
        f.write("".join(h.ljust(col_w) for h in headers) + "\n")

        rows = [
            ("Токены вход", "input_tokens"),
            ("Токены выход", "output_tokens"),
            ("Стоимость", "cost_usd"),
            ("Время", "duration_ms"),
        ]

        for label, key in rows:
            parts = [label.ljust(col_w)]
            for s in stats:
                vals = stats[s]
                if not vals:
                    continue
                values = [float(m[key]) for m in vals]
                avg = sum(values) / len(values)
                if key == "cost_usd":
                    parts.append(f"${avg:.4f}".ljust(col_w))
                elif key == "duration_ms":
                    parts.append(f"{avg / 1000:.1f} сек".ljust(col_w))
                else:
                    parts.append(f"{avg:,.0f}".replace(",", " ").ljust(col_w))
            f.write("".join(parts) + "\n")

        total_cost = sum(
            float(m["cost_usd"]) for vals in stats.values() for m in vals
        )
        f.write(f"\nTotal cost: ${total_cost:.4f}\n")
