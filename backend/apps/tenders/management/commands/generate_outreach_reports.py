"""
Генерация PDF outreach-отчётов по CSV от prepare_outreach_list.py.

Запуск:
    python manage.py generate_outreach_reports \
        --csv outreach_list.csv \
        --output-dir outreach_reports/ \
        --limit 20 \
        --skip-existing \
        --inn 6658037917
"""

import csv
import gc
import json
import logging
import re
import time
from pathlib import Path
from types import SimpleNamespace

from django import db
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


def _sanitize(name: str) -> str:
    return re.sub(r"[^\w\-]", "_", name)[:50]


class Command(BaseCommand):
    help = "Генерирует PDF outreach-отчёты: 3 тендера на компанию из CSV"

    def add_arguments(self, parser):
        parser.add_argument("--csv", required=True, help="Путь к outreach_list.csv")
        parser.add_argument("--output-dir", default="outreach_reports", help="Папка для PDF")
        parser.add_argument("--limit", type=int, default=None, help="Максимум компаний")
        parser.add_argument("--skip-existing", action="store_true", help="Пропустить уже созданные PDF")
        parser.add_argument("--inn", help="Обработать только одну компанию по ИНН")

    def handle(self, *args, **options):
        from celery import current_app
        current_app.conf.task_always_eager = True

        from apps.documents.models import TenderDocument
        from apps.documents.tasks import download_and_parse_documents
        from apps.search.hyde import build_direction_vector
        from apps.search.services import qdrant
        from apps.tenders.models import Tender
        from apps.tenders.outreach_pdf import render_outreach_pdf
        from apps.tenders.summary_v2.pipeline import generate_tender_summary_v2
        from apps.users.dadata import enrich_company_by_inn

        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        companies = self._read_csv(options["csv"])
        self.stdout.write(f"Загружено {len(companies)} компаний из CSV")

        if options["inn"]:
            companies = [c for c in companies if c["inn"] == options["inn"]]
            if not companies:
                self.stderr.write(f"ИНН {options['inn']} не найден в CSV")
                return

        if options["limit"]:
            companies = companies[: options["limit"]]

        log_path = output_dir / "outreach_log.csv"
        log_fields = ["inn", "company_name", "status", "tenders_found", "pdf_path", "error"]
        log_rows = []

        ok = skip = fail = 0

        for i, company in enumerate(companies, 1):
            inn = company["inn"]
            name = company["company_name"]
            self.stdout.write(f"[{i}/{len(companies)}] {inn} {name}")

            pdf_path = output_dir / f"{inn}.pdf"

            if options["skip_existing"] and pdf_path.exists():
                self.stdout.write("  SKIP (already exists)")
                skip += 1
                log_rows.append({"inn": inn, "company_name": name, "status": "skipped",
                                  "tenders_found": "", "pdf_path": str(pdf_path), "error": ""})
                continue

            selected = None
            pdf_buf = None
            try:
                selected = self._process_company(
                    company, qdrant, enrich_company_by_inn,
                    build_direction_vector, Tender, TenderDocument,
                    download_and_parse_documents, generate_tender_summary_v2,
                )

                if not selected:
                    self.stdout.write("  WARN: 0 подходящих тендеров — пропускаем")
                    fail += 1
                    log_rows.append({"inn": inn, "company_name": name, "status": "no_tenders",
                                      "tenders_found": 0, "pdf_path": "", "error": ""})
                    continue

                pdf_buf = render_outreach_pdf(
                    company_name=name,
                    company_inn=inn,
                    company_emails=company.get("emails", ""),
                    tenders=selected,
                )
                pdf_path.write_bytes(pdf_buf.read())
                self.stdout.write(f"  OK: {len(selected)} тендеров → {pdf_path}")
                ok += 1
                log_rows.append({"inn": inn, "company_name": name, "status": "ok",
                                  "tenders_found": len(selected), "pdf_path": str(pdf_path), "error": ""})

            except Exception as e:
                logger.exception("Company %s failed", inn)
                self.stderr.write(f"  FAIL: {e}")
                fail += 1
                log_rows.append({"inn": inn, "company_name": name, "status": "failed",
                                  "tenders_found": 0, "pdf_path": "", "error": str(e)})

            finally:
                del selected, pdf_buf
                db.reset_queries()
                db.close_old_connections()
                gc.collect()

        # Лог
        with log_path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=log_fields)
            w.writeheader()
            w.writerows(log_rows)

        self.stdout.write(
            f"\nГотово: ✓{ok} пропущено={skip} ошибок={fail}. Лог: {log_path}"
        )

    def _read_csv(self, path: str) -> list[dict]:
        rows = []
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                won_products = json.loads(row.get("won_products") or "[]")
                okpd_codes = json.loads(row.get("okpd_codes") or "[]")
                rows.append({
                    "inn": row["inn"].strip(),
                    "company_name": row.get("company_name", "").strip(),
                    "emails": row.get("emails", ""),
                    "phones": row.get("phones", ""),
                    "director": row.get("director", ""),
                    "region": row.get("region", ""),
                    "won_products": won_products,
                    "okpd_codes": okpd_codes,
                })
        return rows

    def _process_company(
        self, company, qdrant, enrich_company_by_inn,
        build_direction_vector, Tender, TenderDocument,
        download_and_parse_documents, generate_tender_summary_v2,
    ) -> list[dict]:
        inn = company["inn"]
        name = company["company_name"]
        won_products = company["won_products"]
        okpd_codes = company["okpd_codes"]

        # ── 1. DaData: получаем ОКВЭД ─────────────────────────────────
        okved_codes: list[str] = []
        region = company.get("region", "")
        try:
            info = enrich_company_by_inn(inn)
            if info:
                okved_codes = info["okved_list"][:10]
                if not region:
                    region = info["region"]
        except Exception as e:
            logger.warning("DaData failed for %s: %s", inn, e)

        keywords = [p[:80] for p in won_products[:5]]
        if not okved_codes:
            keywords += [c for c in okpd_codes[:5] if c not in keywords]

        direction = SimpleNamespace(
            id=0,
            name=name,
            okved_codes=okved_codes,
            keywords=keywords,
            description="",
        )

        # ── 2. HyDE → вектор ──────────────────────────────────────────
        t0 = time.monotonic()
        avg_vector, _ = build_direction_vector(direction)
        self.stdout.write(f"  HyDE: {time.monotonic()-t0:.1f}s")

        # ── 3. Поиск кандидатов в Qdrant — берём 10, не 20 ───────────
        candidates = qdrant.search_tenders(avg_vector, limit=10, status="active")
        self.stdout.write(f"  Кандидатов: {len(candidates)}")

        # ── 4. Итерируем, ищем 3 тендера с документами + AI-резюме ───
        selected: list[dict] = []

        for cand in candidates:
            if len(selected) >= 3:
                break

            tender = None
            try:
                tender = Tender.objects.select_related("customer").get(pk=cand["id"])
            except Tender.DoesNotExist:
                continue

            has_docs = TenderDocument.objects.filter(
                tender=tender,
                parse_status=TenderDocument.ParseStatus.DONE,
            ).exclude(parsed_text="").exists()

            if not has_docs:
                self.stdout.write(f"    Скачиваем доки для #{tender.number} ...")
                try:
                    download_and_parse_documents.apply(args=[tender.id])
                except Exception as e:
                    logger.warning("Doc download failed for %s: %s", tender.id, e)

                has_docs = TenderDocument.objects.filter(
                    tender=tender,
                    parse_status=TenderDocument.ParseStatus.DONE,
                ).exclude(parsed_text="").exists()

            if not has_docs:
                self.stdout.write(f"    #{tender.number}: нет доков → пропускаем")
                del tender
                continue

            try:
                sv2 = generate_tender_summary_v2(tender.id)
                # Сохраняем только нужные поля — ORM объект не держим
                tender_dto = SimpleNamespace(
                    number=tender.number,
                    title=tender.title,
                    nmck=tender.nmck,
                    region=tender.region,
                    deadline_at=tender.deadline_at,
                    customer=SimpleNamespace(name=tender.customer.name) if tender.customer else None,
                )
                selected.append({"tender": tender_dto, "summary": sv2.summary})
                del tender, sv2, tender_dto
                gc.collect()
                self.stdout.write(f"    резюме готово ({len(selected)}/3)")
            except Exception as e:
                logger.warning("Summary failed for tender %s: %s", tender.id, e)
                self.stdout.write(f"    резюме ошибка: {e}")
                del tender

        return selected
