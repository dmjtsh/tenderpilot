import time
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.tenders.models import Tender

QUESTIONS = [
    "Какой аванс?",
    "Какое обеспечение заявки и контракта?",
    "Каков срок выполнения работ?",
    "Когда дедлайн подачи заявки?",
    "Какие лицензии нужны?",
    "Кто заказчик?",
    "Что нужно сделать?",
    "Какие штрафы за просрочку?",
    "Можно ли субподряд?",
    "Каков гарантийный срок?",
    "Какие критерии оценки?",
    "Какие документы для подачи заявки?",
    "Где работы выполняются?",
    "Применим ли антидемпинг?",
    "Какой источник финансирования?",
]


class Command(BaseCommand):
    help = "A/B test: RAG chat vs Full Context chat"

    def add_arguments(self, parser):
        parser.add_argument("--tender-id", type=int, default=18807)
        parser.add_argument("--output", type=str, default="")

    def handle(self, *args, **options):
        from apps.documents.services import answer_question
        from apps.tenders.chat_service import chat_with_tender_full_context
        from apps.tenders.services import get_llm_client, calculate_cost

        tender_id = options["tender_id"]
        tender = Tender.objects.select_related("customer").get(pk=tender_id)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = options["output"] or f"ab_chat_{tender_id}_{ts}.txt"

        lines = []
        sep = "═" * 55
        thin = "─" * 55

        lines.append(sep)
        lines.append("A/B ТЕСТ: RAG vs FULL CONTEXT CHAT (v4 — prompt fix)")
        lines.append(f"Тендер: {tender_id} — {tender.title[:80]}")
        lines.append(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append(sep)
        lines.append("")

        rag_times = []
        full_times = []
        rag_answered = 0
        full_answered = 0
        full_input_tokens = []
        full_output_tokens = []
        full_costs: list[Decimal] = []

        for i, q in enumerate(QUESTIONS, 1):
            self.stdout.write(f"Q{i}/{len(QUESTIONS)}: {q}")
            lines.append(thin)
            lines.append(f"Q{i}: {q}")
            lines.append("")

            # RAG
            t0 = time.time()
            try:
                rag_result = answer_question(tender_id, q)
                rag_answer = rag_result.get("answer") or "(нет ответа)"
                rag_sources = [s["filename"] for s in rag_result.get("sources", [])]
                if rag_result.get("answer"):
                    rag_answered += 1
            except Exception as e:
                rag_answer = f"ОШИБКА: {e}"
                rag_sources = []
            rag_t = time.time() - t0
            rag_times.append(rag_t)

            lines.append(f"RAG ({rag_t:.1f}s):")
            lines.append(rag_answer)
            if rag_sources:
                lines.append(f"Источники: {', '.join(dict.fromkeys(rag_sources))}")
            lines.append("")

            # Full Context — with metrics
            t0 = time.time()
            full_answer = ""
            model_used = "deepseek-chat"
            in_tok = 0
            out_tok = 0
            try:
                from apps.tenders.chat_service import _get_docs_text, _build_system_prompt
                from apps.documents.services import count_tokens

                t_obj = Tender.objects.select_related("customer").get(pk=tender_id)
                docs_text = _get_docs_text(t_obj)
                system_prompt = _build_system_prompt(t_obj)
                user_content = f"{q}\n\nДокументация тендера:\n{docs_text}"

                in_tok = count_tokens(system_prompt) + count_tokens(user_content)

                chunks = list(chat_with_tender_full_context(tender_id, q, []))
                full_answer = "".join(chunks)
                out_tok = count_tokens(full_answer)

                if full_answer:
                    full_answered += 1
            except Exception as e:
                full_answer = f"ОШИБКА: {e}"
            full_t = time.time() - t0
            full_times.append(full_t)
            full_input_tokens.append(in_tok)
            full_output_tokens.append(out_tok)
            cost = calculate_cost(model_used, in_tok, out_tok)
            full_costs.append(cost)

            lines.append(f"FULL ({full_t:.1f}s | {model_used} | {in_tok:,} in / {out_tok:,} out | ${cost:.4f}):")
            lines.append(full_answer)
            lines.append("")

        total_in = sum(full_input_tokens)
        total_out = sum(full_output_tokens)
        total_cost = sum(full_costs, Decimal("0"))

        lines.append(sep)
        lines.append("ИТОГО")
        lines.append(
            f"RAG:  avg {sum(rag_times)/len(rag_times):.1f}s, "
            f"total {sum(rag_times):.0f}s, "
            f"ответил {rag_answered}/{len(QUESTIONS)}"
        )
        lines.append(
            f"FULL: avg {sum(full_times)/len(full_times):.1f}s, "
            f"total {sum(full_times):.0f}s, "
            f"ответил {full_answered}/{len(QUESTIONS)}"
        )
        lines.append(f"FULL tokens: {total_in:,} in / {total_out:,} out")
        lines.append(f"FULL cost:   ${total_cost:.4f} ({len(QUESTIONS)} вопросов)")
        lines.append(f"FULL avg:    ${total_cost/len(QUESTIONS):.4f}/вопрос")
        lines.append(sep)

        with open(output_path, "w") as f:
            f.write("\n".join(lines))

        self.stdout.write(self.style.SUCCESS(f"\nРезультат записан в {output_path}"))
