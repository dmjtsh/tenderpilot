import json
from datetime import datetime

import yaml
from django.core.management.base import BaseCommand
from django.utils import timezone
from tqdm import tqdm

from apps.documents.services import answer_question_with_variant
from apps.tenders.models import Experiment, PromptTemplate, SummaryExperiment, Tender


DEFAULT_QUESTIONS = [
    "Какие штрафы за просрочку?",
    "Когда оплата по контракту?",
    "Какие документы нужны для участия?",
    "Кто фактический заказчик?",
    "Какой гарантийный срок?",
    "Какие СРО или лицензии нужны?",
]


class Command(BaseCommand):
    help = "Run a QA experiment comparing models on RAG chat questions"

    def add_arguments(self, parser) -> None:
        parser.add_argument("--config", type=str, required=True)
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--tender-ids", type=str, required=True,
                            help="Comma-separated tender IDs")

    def handle(self, *args, **options) -> None:
        config_path: str = options["config"]
        output_path: str = options["output"]
        tender_ids_raw: str = options["tender_ids"]

        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        name = config.get("name", "Unnamed QA experiment")
        description = config.get("description", "")
        variants = config.get("variants", [])
        questions = config.get("questions", DEFAULT_QUESTIONS)

        if not variants:
            self.stderr.write(self.style.ERROR("No variants in config"))
            return

        for v in variants:
            if "label" not in v or "name" not in v:
                self.stderr.write(self.style.ERROR(f"Variant missing label/name: {v}"))
                return
            slug = v.get("prompt_template", "chat_qa_v1")
            if not PromptTemplate.objects.filter(name=slug, is_active=True).exists():
                self.stderr.write(self.style.ERROR(f"PromptTemplate '{slug}' not found"))
                return

        ids = [int(x.strip()) for x in tender_ids_raw.split(",") if x.strip()]
        tender_ids = list(Tender.objects.filter(id__in=ids).values_list("id", flat=True))
        tender_ids = [tid for tid in ids if tid in set(tender_ids)]

        if not tender_ids:
            self.stderr.write(self.style.ERROR("No tenders found"))
            return

        experiment = Experiment.objects.create(
            name=name,
            description=description,
            tender_ids=tender_ids,
            variants=variants,
        )

        if not output_path:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            slug = name.lower().replace(" ", "_")[:40]
            output_path = f"qa_experiment_{slug}_{ts}.txt"

        tenders = list(Tender.objects.select_related("customer").filter(id__in=tender_ids))
        tender_map = {t.id: t for t in tenders}
        tenders = [tender_map[tid] for tid in tender_ids if tid in tender_map]

        total = len(tenders) * len(questions) * len(variants)
        self.stdout.write(
            f"QA Experiment '{name}' (id={experiment.id}): "
            f"{len(tenders)} tenders × {len(questions)} questions × {len(variants)} variants = {total} runs"
        )

        experiment.status = Experiment.Status.RUNNING
        experiment.save(update_fields=["status"])

        stats: dict[str, list[dict]] = {v["label"]: [] for v in variants}
        errors = 0

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"{'=' * 72}\n")
            f.write(f"QA ЭКСПЕРИМЕНТ: {name}\n")
            f.write(f"Запущен: {timezone.now().strftime('%d %B %Y, %H:%M')}\n")
            if description:
                f.write(f"Описание: {description}\n")
            f.write(f"{'=' * 72}\n\n")

            f.write("ВАРИАНТЫ:\n")
            for v in variants:
                f.write(f"  [{v['label']}] {v['name']} — {v.get('model', '?')}\n")
            f.write(f"\nТендеров: {len(tenders)}, вопросов: {len(questions)}\n")
            f.write(f"Всего запусков: {total}\n\n")

            progress = tqdm(total=total, desc="QA runs")

            for tender in tenders:
                f.write(f"{'=' * 72}\n")
                f.write(f"ТЕНДЕР #{tender.id} — {tender.title[:80]}\n")
                f.write(f"Номер: {tender.number}\n")
                if tender.customer:
                    f.write(f"Заказчик: {tender.customer.name}\n")
                f.write(f"{'=' * 72}\n\n")

                for question in questions:
                    f.write(f"{'━' * 72}\n")
                    f.write(f"ВОПРОС: {question}\n")
                    f.write(f"{'━' * 72}\n")

                    for variant in variants:
                        label = variant["label"]
                        try:
                            result = answer_question_with_variant(tender.id, question, variant)
                            metrics = result["metrics"]
                            answer = result.get("answer") or "(нет ответа)"
                            sources = result.get("sources", [])

                            SummaryExperiment.objects.create(
                                tender=tender,
                                experiment=experiment,
                                variant_label=label,
                                variant_name=variant["name"],
                                strategy="rag",
                                model=metrics["model"],
                                actual_model=metrics.get("actual_model", ""),
                                input_tokens=metrics["input_tokens"],
                                output_tokens=metrics["output_tokens"],
                                cost_usd=metrics["cost_usd"],
                                duration_ms=metrics["duration_ms"],
                                result={
                                    "question": question,
                                    "answer": answer,
                                    "sources_count": len(sources),
                                    "source_filenames": list({s["filename"] for s in sources}),
                                },
                            )

                            stats[label].append(metrics)

                            actual = metrics.get("actual_model", "")
                            model_str = metrics["model"]
                            if actual and actual != model_str:
                                model_str += f" ({actual})"

                            f.write(f"\n[{label}] {variant['name']} — {model_str}\n")
                            f.write(f"    {metrics['input_tokens']} вх / {metrics['output_tokens']} вых · "
                                    f"${metrics['cost_usd']:.4f} · {metrics['duration_ms'] / 1000:.1f}с\n")
                            f.write(f"    Источники: {', '.join(s['filename'] for s in sources[:3])}\n")
                            f.write(f"    Ответ: {answer}\n")

                        except Exception as exc:
                            errors += 1
                            f.write(f"\n[{label}] ОШИБКА: {exc}\n")
                            self.stderr.write(f"  Error tender={tender.id} q='{question[:30]}' [{label}]: {exc}")

                        progress.update(1)

                    f.write("\n")
                f.write("\n")
                f.flush()

            progress.close()

            f.write(f"{'=' * 72}\n")
            f.write("СВОДКА\n")
            f.write(f"{'=' * 72}\n")
            f.write(f"Завершён: {timezone.now().strftime('%d %B %Y, %H:%M')}\n")
            f.write(f"Запусков: {sum(len(v) for v in stats.values())}\n")
            if errors:
                f.write(f"Ошибок: {errors}\n")

            f.write("\nСредние метрики:\n")
            col_w = 25
            header = "".ljust(col_w)
            for v in variants:
                header += f"[{v['label']}] {v['name']}".ljust(col_w)
            f.write(header + "\n")

            for row_label, key in [("Вх. токены", "input_tokens"), ("Вых. токены", "output_tokens"),
                                   ("Стоимость", "cost_usd"), ("Время", "duration_ms")]:
                parts = [row_label.ljust(col_w)]
                for v in variants:
                    vals = [float(m[key]) for m in stats[v["label"]]]
                    avg = sum(vals) / len(vals) if vals else 0
                    if key == "cost_usd":
                        parts.append(f"${avg:.4f}".ljust(col_w))
                    elif key == "duration_ms":
                        parts.append(f"{avg / 1000:.1f}с".ljust(col_w))
                    else:
                        parts.append(f"{avg:,.0f}".replace(",", " ").ljust(col_w))
                f.write("".join(parts) + "\n")

            total_cost = sum(float(m["cost_usd"]) for runs in stats.values() for m in runs)
            f.write(f"\nОбщая стоимость: ${total_cost:.4f}\n")

        experiment.status = Experiment.Status.COMPLETED
        experiment.completed_at = timezone.now()
        experiment.save(update_fields=["status", "completed_at"])

        self.stdout.write(self.style.SUCCESS(f"Done. Report: {output_path}"))
