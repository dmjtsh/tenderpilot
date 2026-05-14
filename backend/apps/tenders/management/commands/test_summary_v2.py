import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Тест AI-резюме v2: отдельный шаг или полный pipeline"

    def add_arguments(self, parser):
        parser.add_argument("--tender-id", type=int, required=True)
        parser.add_argument(
            "--step",
            choices=["financial", "timeline", "requirements", "work", "risks", "customer"],
            default="financial",
        )
        parser.add_argument("--model", default="deepseek-chat")
        parser.add_argument("--pipeline-mode", action="store_true", help="Запустить все 6 шагов")

    def handle(self, *args, **options):
        tender_id = options["tender_id"]
        model = options["model"]

        if options["pipeline_mode"]:
            self._run_pipeline(tender_id, model)
        else:
            self._run_single_step(tender_id, options["step"], model)

    def _run_single_step(self, tender_id: int, step: str, model: str):
        from apps.tenders.summary_v2.pipeline import generate_step

        self.stdout.write(f"Тендер {tender_id}, шаг: {step}, модель: {model}")
        self.stdout.write("Загружаю документы...")

        try:
            data = generate_step(tender_id, step, model=model)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Ошибка: {e}"))
            return

        result = data["result"]
        metrics = data["metrics"]

        self.stdout.write(self.style.SUCCESS(f"\nРезультат ({step}):"))
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        self.stdout.write("\n--- Метрики ---")
        self.stdout.write(f"Модель:       {metrics['actual_model'] or metrics['model']}")
        self.stdout.write(f"Input tokens: {metrics['input_tokens']}")
        self.stdout.write(f"Output tokens: {metrics['output_tokens']}")
        self.stdout.write(f"Duration:     {metrics['duration_ms']}ms")

    def _run_pipeline(self, tender_id: int, model: str):
        from apps.tenders.summary_v2.pipeline import generate_tender_summary_v2

        self.stdout.write(f"Тендер {tender_id}, PIPELINE MODE, модель: {model}")
        self.stdout.write("Запускаю 6 шагов (5 параллельно + risks)...")

        try:
            obj = generate_tender_summary_v2(tender_id, model=model)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Ошибка: {e}"))
            import traceback
            traceback.print_exc()
            return

        self.stdout.write(self.style.SUCCESS(f"\n{'='*60}"))
        self.stdout.write(self.style.SUCCESS("PIPELINE ЗАВЕРШЁН"))
        self.stdout.write(f"{'='*60}")
        self.stdout.write(f"Время:        {obj.generation_time_ms}ms ({obj.generation_time_ms/1000:.1f}с)")
        self.stdout.write(f"Input tokens: {obj.total_input_tokens}")
        self.stdout.write(f"Output tokens: {obj.total_output_tokens}")
        self.stdout.write(f"Стоимость:    ${obj.total_cost_usd}")
        self.stdout.write(f"Модель:       {obj.model}")

        self.stdout.write(f"\n--- Метрики по шагам ---")
        for step_name, m in obj.step_metrics.items():
            dur = m.get("duration_ms", 0)
            inp = m.get("input_tokens", 0)
            out = m.get("output_tokens", 0)
            self.stdout.write(f"  {step_name:15s}  {dur:>6d}ms  in={inp:>6d}  out={out:>5d}")

        self.stdout.write(f"\n--- Результат ---")
        self.stdout.write(json.dumps(obj.summary, ensure_ascii=False, indent=2, default=str))
