import json
import logging
import re
import time
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db.models import Count, Sum
from django.utils import timezone

from .models import Customer, Tender

logger = logging.getLogger(__name__)


_PROCEDURE_URL_MAP = [
    (r"/notice/ea(?:20|44)/", Tender.ProcedureType.AUCTION),
    (r"/notice/ok(?:20|44)/", Tender.ProcedureType.CONTEST),
    (r"/notice/zk(?:20|44)/", Tender.ProcedureType.REQUEST_QUOTATIONS),
    (r"/notice/(?:ezt20|zp44)/", Tender.ProcedureType.REQUEST_PROPOSALS),
]


def detect_procedure_type(source_url: str) -> str:
    for pattern, proc_type in _PROCEDURE_URL_MAP:
        if re.search(pattern, source_url):
            return proc_type
    return Tender.ProcedureType.OTHER

SUMMARY_PROMPT = """Ты эксперт по госзакупкам России.
Определи тип тендера: строительство / поставка / услуги / проектирование / IT / другое.

ДАННЫЕ ТЕНДЕРА:
Название: {title}
НМЦК: {nmck}
Дней до дедлайна: {days_left}
Регион: {region}
ОКПД: {okpd_names}
Тип закупки: {law_type}
Обеспечение заявки: {bid_security}
Обеспечение контракта: {contract_security}

ДАННЫЕ ЗАКАЗЧИКА:
Название: {customer_name}
ИНН: {customer_inn}
Регион заказчика: {customer_region}
Основной ОКВЭД: {customer_okved}
Тендеров в нашей базе: {customer_tender_count}
Общий объём закупок: {customer_total_volume}

{docs_section}

Проанализируй и верни JSON без markdown:
{{
  "customer_analysis": {{
    "notes": ["заметки о заказчике если есть"]
  }},
  "work_description": {{
    "essence": "одно-два предложения что конкретно нужно сделать",
    "payment_terms": "условия оплаты: аванс, поэтапная, по факту — или null",
    "execution_period": "конкретный срок выполнения или null",
    "experience_requirements": ["конкретное требование к опыту/квалификации с цифрами"],
    "deadline_info": "информация о сроке подачи заявки или null"
  }},
  "key_risks": {{
    "certifications": ["требуемые лицензии, допуски, сертификаты"],
    "financial_risks": ["финансовые риски: высокое обеспечение, штрафы, пени с размером"],
    "technical_risks": ["технические риски: сжатые сроки, запрет субподряда, сложные условия"],
    "unusual_conditions": ["необычные или нестандартные условия"]
  }},
  "required_documents": {{
    "mandatory": ["обязательный документ в составе заявки"],
    "optional": ["рекомендуемый/желательный документ"],
    "special_forms": ["особая форма или шаблон заказчика"]
  }},
  "verdict": "участвовать | изучить | пропустить",
  "verdict_reason": "одно предложение",
  "tender_type": "строительство | поставка | услуги | проектирование | IT | другое",
  "urgency": "нормально | сжато | очень сжато"
}}

ПРАВИЛА:
- Все числовые значения копируй ТОЧНО как в документах — не округляй, не конвертируй
- НЕ придумывай требования которых нет в документах
- НЕ пиши общие фразы — только конкретика с цифрами
- Обеспечение контракта <= 15% НЕ является риском
- Обеспечение контракта > 15% → добавь в financial_risks с точным процентом
- required_documents: извлекай из документации или инструкции участнику
- Если документов нет — секции будут пустыми, это нормально
- customer_analysis.notes: нетипичный ОКВЭД для данного типа тендера, малый объём закупок и т.д."""

VERDICT_MAP: dict[str, str] = {
    "участвовать": "go",
    "изучить": "maybe",
    "пропустить": "pass",
}

URGENCY_MAP: dict[str, str] = {
    "нормально": "low",
    "сжато": "medium",
    "очень сжато": "high",
}


def _get_customer_context(tender: Tender) -> dict:
    result = {"name": "", "inn": "", "region": "", "okved_main": "", "tender_count": 0, "total_volume": 0}
    if not tender.customer:
        return result
    customer = tender.customer
    result["name"] = customer.name
    result["inn"] = customer.inn or ""
    result["region"] = customer.region or tender.region or ""
    stats = Tender.objects.filter(customer=customer).aggregate(count=Count("id"), total=Sum("nmck"))
    result["tender_count"] = stats["count"] or 0
    result["total_volume"] = float(stats["total"] or 0)
    if customer.inn:
        try:
            from apps.users.dadata import enrich_company_by_inn
            info = enrich_company_by_inn(customer.inn)
            if info and info["okved_main"]:
                from apps.tenders.okved import okved_to_text
                result["okved_main"] = f'{info["okved_main"]} — {okved_to_text([info["okved_main"]])}'
        except Exception:
            logger.warning("DaData enrichment failed for INN %s", customer.inn, exc_info=True)
    return result


SUMMARY_MODEL = "deepseek-chat"
SUMMARY_FALLBACK_MODEL = "gpt-4o-mini"


def generate_tender_summary(tender: Tender) -> dict:
    from apps.tenders.okved import okved_to_text
    from apps.documents.services import get_summary_context

    days_left = None
    if tender.deadline_at:
        days_left = (tender.deadline_at.date() - timezone.now().date()).days

    bid_security = (
        "не требуется" if tender.bid_security_required is False
        else f"{tender.bid_security_amount:,.0f} ₽".replace(",", " ") if tender.bid_security_amount
        else "не указано"
    )
    contract_security = (
        f"{tender.contract_security_amount:,.0f} ₽ ({tender.contract_security_percent}%)".replace(",", " ")
        if tender.contract_security_amount and tender.contract_security_percent
        else f"{tender.contract_security_percent}%" if tender.contract_security_percent
        else "не указано"
    )

    cust = _get_customer_context(tender)

    ctx = get_summary_context(tender)
    source = ctx["source"]
    has_docs = source in ("rag", "text", "full_tz")

    if source == "full_tz":
        docs_section = f"ДОКУМЕНТАЦИЯ (техзадание целиком + релевантные разделы других документов):\n{ctx['context']}"
    elif source == "rag":
        docs_section = f"ДОКУМЕНТАЦИЯ (релевантные разделы):\n{ctx['context']}"
    elif source == "text":
        docs_section = f"ДОКУМЕНТАЦИЯ (полный текст):\n{ctx['context']}"
    else:
        docs_section = "ВНИМАНИЕ: документы не загружены, анализ только по метаданным."

    cust_total_fmt = f"{cust['total_volume']:,.0f} ₽".replace(",", " ") if cust["total_volume"] else "нет данных"

    prompt = SUMMARY_PROMPT.format(
        title=tender.title,
        nmck=f"{tender.nmck:,.0f} ₽".replace(",", " ") if tender.nmck else "не указана",
        days_left=f"{days_left}" if days_left is not None else "не указан",
        region=tender.region or "не указан",
        okpd_names=okved_to_text(tender.okpd_codes or []) or "не указан",
        law_type=tender.law_type or "не указан",
        bid_security=bid_security,
        contract_security=contract_security,
        customer_name=cust["name"] or "не указан",
        customer_inn=cust["inn"] or "не указан",
        customer_region=cust["region"] or "не указан",
        customer_okved=cust["okved_main"] or "не указан",
        customer_tender_count=cust["tender_count"],
        customer_total_volume=cust_total_fmt,
        docs_section=docs_section,
    )

    model_name = SUMMARY_MODEL
    try:
        client = get_llm_client(model_name)
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2800,
            temperature=0.3,
        )
        raw = response.choices[0].message.content.strip()
    except Exception:
        logger.warning("DeepSeek API failed for tender %d, falling back to %s", tender.id, SUMMARY_FALLBACK_MODEL)
        model_name = SUMMARY_FALLBACK_MODEL
        client = get_llm_client(model_name)
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2800,
            temperature=0.3,
        )
        raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    gpt = json.loads(raw)

    verdict_raw = gpt.get("verdict", "изучить")
    urgency_raw = gpt.get("urgency", "нормально")

    key_risks = gpt.get("key_risks") or {}
    financial_risks = key_risks.get("financial_risks") or []
    contract_pct = tender.contract_security_percent
    if contract_pct is not None:
        has_flag = any("обеспечен" in f.lower() for f in financial_risks)
        if contract_pct > 15 and not has_flag:
            financial_risks.append(f"Обеспечение контракта {contract_pct}% (выше 15%)")
        elif contract_pct <= 15:
            financial_risks = [f for f in financial_risks if "обеспечен" not in f.lower()]

    customer_analysis = gpt.get("customer_analysis") or {}
    work_description = gpt.get("work_description") or {}
    required_documents = gpt.get("required_documents") or {}

    return {
        "version": 2,
        "customer_analysis": {
            "name": cust["name"],
            "inn": cust["inn"],
            "region": cust["region"],
            "okved_main": cust["okved_main"],
            "tender_count": cust["tender_count"],
            "total_volume": cust["total_volume"],
            "notes": customer_analysis.get("notes") or [],
        },
        "work_description": {
            "essence": work_description.get("essence", ""),
            "payment_terms": work_description.get("payment_terms"),
            "execution_period": work_description.get("execution_period"),
            "experience_requirements": work_description.get("experience_requirements") or [],
            "deadline_info": work_description.get("deadline_info"),
        },
        "key_risks": {
            "certifications": key_risks.get("certifications") or [],
            "financial_risks": financial_risks,
            "technical_risks": key_risks.get("technical_risks") or [],
            "unusual_conditions": key_risks.get("unusual_conditions") or [],
        },
        "required_documents": {
            "mandatory": required_documents.get("mandatory") or [],
            "optional": required_documents.get("optional") or [],
            "special_forms": required_documents.get("special_forms") or [],
        },
        "verdict": VERDICT_MAP.get(verdict_raw, verdict_raw),
        "verdict_reason": gpt.get("verdict_reason", ""),
        "tender_type": gpt.get("tender_type", "другое"),
        "has_docs": has_docs,
        "days_left": days_left,
        "urgency": URGENCY_MAP.get(urgency_raw, urgency_raw),
    }


def get_or_create_summary(tender: Tender) -> dict:
    if tender.ai_summary:
        try:
            data = json.loads(tender.ai_summary)
            if data.get("version") == 2:
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    summary = generate_tender_summary(tender)
    tender.ai_summary = json.dumps(summary, ensure_ascii=False)
    tender.save(update_fields=["ai_summary"])
    return summary


MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-5-nano": {"input": 0.05, "output": 0.40},
    "deepseek-chat": {"input": 0.14, "output": 0.28},
}


def get_llm_client(model: str):
    from openai import OpenAI
    if model.startswith("deepseek"):
        return OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )
    return OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL or None,
    )


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["gpt-4o-mini"])
    cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
    return Decimal(str(round(cost, 6)))


def _build_context_vars(tender: Tender, strategy: str) -> tuple[dict, dict]:
    """Build prompt context variables and truncation metadata.
    Returns (context_vars, truncation_info).
    """
    from apps.tenders.okved import okved_to_text
    from apps.documents.services import get_summary_context, get_full_context

    days_left = None
    if tender.deadline_at:
        days_left = (tender.deadline_at.date() - timezone.now().date()).days

    bid_security = (
        "не требуется" if tender.bid_security_required is False
        else f"{tender.bid_security_amount:,.0f} ₽".replace(",", " ") if tender.bid_security_amount
        else "не указано"
    )
    contract_security = (
        f"{tender.contract_security_amount:,.0f} ₽ ({tender.contract_security_percent}%)".replace(",", " ")
        if tender.contract_security_amount and tender.contract_security_percent
        else f"{tender.contract_security_percent}%" if tender.contract_security_percent
        else "не указано"
    )

    cust = _get_customer_context(tender)

    was_truncated = False
    truncated_reason = ""
    original_total_tokens = 0

    if strategy == "full":
        ctx = get_full_context(tender)
        was_truncated = ctx.get("was_truncated", False)
        truncated_reason = ctx.get("truncated_reason", "")
        original_total_tokens = ctx.get("original_total_tokens", 0)
        source = ctx["source"]
        if source == "full":
            docs_section = f"ДОКУМЕНТАЦИЯ (полный текст всех документов):\n{ctx['context']}"
        else:
            docs_section = "ВНИМАНИЕ: документы не загружены, анализ только по метаданным."
    else:
        ctx = get_summary_context(tender)
        source = ctx["source"]
        if source == "full_tz":
            docs_section = f"ДОКУМЕНТАЦИЯ (техзадание целиком + релевантные разделы других документов):\n{ctx['context']}"
        elif source == "rag":
            docs_section = f"ДОКУМЕНТАЦИЯ (релевантные разделы):\n{ctx['context']}"
        elif source == "text":
            docs_section = f"ДОКУМЕНТАЦИЯ (полный текст):\n{ctx['context']}"
        else:
            docs_section = "ВНИМАНИЕ: документы не загружены, анализ только по метаданным."

    has_docs = source not in ("none",)
    cust_total_fmt = f"{cust['total_volume']:,.0f} ₽".replace(",", " ") if cust["total_volume"] else "нет данных"

    context_vars = {
        "title": tender.title,
        "nmck": f"{tender.nmck:,.0f} ₽".replace(",", " ") if tender.nmck else "не указана",
        "days_left": f"{days_left}" if days_left is not None else "не указан",
        "region": tender.region or "не указан",
        "okpd_names": okved_to_text(tender.okpd_codes or []) or "не указан",
        "law_type": tender.law_type or "не указан",
        "bid_security": bid_security,
        "contract_security": contract_security,
        "customer_name": cust["name"] or "не указан",
        "customer_inn": cust["inn"] or "не указан",
        "customer_region": cust["region"] or "не указан",
        "customer_okved": cust["okved_main"] or "не указан",
        "customer_tender_count": cust["tender_count"],
        "customer_total_volume": cust_total_fmt,
        "docs_section": docs_section,
    }

    truncation_info = {
        "was_truncated": was_truncated,
        "truncated_reason": truncated_reason,
        "original_total_tokens": original_total_tokens,
        "has_docs": has_docs,
        "days_left": days_left,
        "cust": cust,
    }

    return context_vars, truncation_info


def _postprocess_gpt_response(raw: str, tender: Tender, truncation_info: dict) -> dict:
    """Parse GPT response and build the v2 summary dict."""
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    gpt = json.loads(raw)

    verdict_raw = gpt.get("verdict", "изучить")
    urgency_raw = gpt.get("urgency", "нормально")

    key_risks = gpt.get("key_risks") or {}
    financial_risks = key_risks.get("financial_risks") or []
    contract_pct = tender.contract_security_percent
    if contract_pct is not None:
        has_flag = any("обеспечен" in f.lower() for f in financial_risks)
        if contract_pct > 15 and not has_flag:
            financial_risks.append(f"Обеспечение контракта {contract_pct}% (выше 15%)")
        elif contract_pct <= 15:
            financial_risks = [f for f in financial_risks if "обеспечен" not in f.lower()]

    cust = truncation_info["cust"]
    customer_analysis = gpt.get("customer_analysis") or {}
    work_description = gpt.get("work_description") or {}
    required_documents = gpt.get("required_documents") or {}

    return {
        "version": 2,
        "customer_analysis": {
            "name": cust["name"], "inn": cust["inn"], "region": cust["region"],
            "okved_main": cust["okved_main"], "tender_count": cust["tender_count"],
            "total_volume": cust["total_volume"],
            "notes": customer_analysis.get("notes") or [],
        },
        "work_description": {
            "essence": work_description.get("essence", ""),
            "payment_terms": work_description.get("payment_terms"),
            "execution_period": work_description.get("execution_period"),
            "experience_requirements": work_description.get("experience_requirements") or [],
            "deadline_info": work_description.get("deadline_info"),
        },
        "key_risks": {
            "certifications": key_risks.get("certifications") or [],
            "financial_risks": financial_risks,
            "technical_risks": key_risks.get("technical_risks") or [],
            "unusual_conditions": key_risks.get("unusual_conditions") or [],
        },
        "required_documents": {
            "mandatory": required_documents.get("mandatory") or [],
            "optional": required_documents.get("optional") or [],
            "special_forms": required_documents.get("special_forms") or [],
        },
        "verdict": VERDICT_MAP.get(verdict_raw, verdict_raw),
        "verdict_reason": gpt.get("verdict_reason", ""),
        "tender_type": gpt.get("tender_type", "другое"),
        "has_docs": truncation_info["has_docs"],
        "days_left": truncation_info["days_left"],
        "urgency": URGENCY_MAP.get(urgency_raw, urgency_raw),
    }


def generate_summary_with_variant(tender: Tender, variant: dict) -> dict:
    from .models import PromptTemplate

    strategy = variant.get("strategy", "rag")
    model_name = variant.get("model", "gpt-4o-mini")
    prompt_slug = variant.get("prompt_template", "summary_v1")

    if strategy == "v2_full":
        from apps.tenders.summary_v2.pipeline import generate_tender_summary_v2
        obj = generate_tender_summary_v2(tender.id, model=model_name)
        return {
            "summary": obj.summary,
            "metrics": {
                "strategy": "v2_full",
                "model": model_name,
                "actual_model": obj.step_metrics.get("work", {}).get("actual_model", ""),
                "prompt_template": "v2_full_builtin",
                "prompt_template_id": None,
                "input_tokens": obj.total_input_tokens,
                "output_tokens": obj.total_output_tokens,
                "cost_usd": float(obj.total_cost_usd),
                "duration_ms": obj.generation_time_ms,
                "was_truncated": False,
                "truncated_reason": "",
                "original_total_tokens": 0,
            },
        }

    if strategy.startswith("v2_"):
        from apps.tenders.summary_v2.pipeline import generate_step_with_metrics
        step = strategy.removeprefix("v2_")
        return generate_step_with_metrics(tender, step, model_name)

    template = PromptTemplate.objects.filter(
        name=prompt_slug, is_active=True,
    ).first()
    if not template:
        raise ValueError(f"PromptTemplate '{prompt_slug}' not found or inactive")

    context_vars, truncation_info = _build_context_vars(tender, strategy)
    prompt = template.user_template.format(**context_vars)

    client = get_llm_client(model_name)
    messages: list[dict] = []
    if template.system_prompt:
        messages.append({"role": "system", "content": template.system_prompt})
    messages.append({"role": "user", "content": prompt})

    reasoning_model = model_name.startswith("gpt-5") or model_name.startswith("o")
    if reasoning_model:
        token_kwargs = {"max_completion_tokens": 16384, "temperature": 1}
    else:
        token_kwargs = {"max_tokens": 2800, "temperature": 0.3}

    start_ns = time.monotonic_ns()
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        **token_kwargs,
    )
    duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000

    raw = response.choices[0].message.content.strip()
    summary = _postprocess_gpt_response(raw, tender, truncation_info)

    actual_model = getattr(response, "model", "") or ""
    if actual_model and actual_model != model_name:
        logger.warning("Model alias resolved: requested=%s actual=%s", model_name, actual_model)

    usage = response.usage
    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0
    cost = calculate_cost(model_name, input_tokens, output_tokens)

    return {
        "summary": summary,
        "metrics": {
            "strategy": strategy,
            "model": model_name,
            "actual_model": actual_model,
            "prompt_template": prompt_slug,
            "prompt_template_id": template.id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
            "duration_ms": duration_ms,
            "was_truncated": truncation_info["was_truncated"],
            "truncated_reason": truncation_info["truncated_reason"],
            "original_total_tokens": truncation_info["original_total_tokens"],
        },
    }


def generate_experiment_summary(tender: Tender, strategy: str = "rag") -> dict:
    from openai import OpenAI
    from apps.tenders.okved import okved_to_text
    from apps.documents.services import get_summary_context, get_full_context

    days_left = None
    if tender.deadline_at:
        days_left = (tender.deadline_at.date() - timezone.now().date()).days

    bid_security = (
        "не требуется" if tender.bid_security_required is False
        else f"{tender.bid_security_amount:,.0f} ₽".replace(",", " ") if tender.bid_security_amount
        else "не указано"
    )
    contract_security = (
        f"{tender.contract_security_amount:,.0f} ₽ ({tender.contract_security_percent}%)".replace(",", " ")
        if tender.contract_security_amount and tender.contract_security_percent
        else f"{tender.contract_security_percent}%" if tender.contract_security_percent
        else "не указано"
    )

    cust = _get_customer_context(tender)

    was_truncated = False
    truncated_reason = ""
    original_total_tokens = 0

    if strategy == "full":
        ctx = get_full_context(tender)
        was_truncated = ctx.get("was_truncated", False)
        truncated_reason = ctx.get("truncated_reason", "")
        original_total_tokens = ctx.get("original_total_tokens", 0)
        source = ctx["source"]
        if source == "full":
            docs_section = f"ДОКУМЕНТАЦИЯ (полный текст всех документов):\n{ctx['context']}"
        else:
            docs_section = "ВНИМАНИЕ: документы не загружены, анализ только по метаданным."
    else:
        ctx = get_summary_context(tender)
        source = ctx["source"]
        if source == "full_tz":
            docs_section = f"ДОКУМЕНТАЦИЯ (техзадание целиком + релевантные разделы других документов):\n{ctx['context']}"
        elif source == "rag":
            docs_section = f"ДОКУМЕНТАЦИЯ (релевантные разделы):\n{ctx['context']}"
        elif source == "text":
            docs_section = f"ДОКУМЕНТАЦИЯ (полный текст):\n{ctx['context']}"
        else:
            docs_section = "ВНИМАНИЕ: документы не загружены, анализ только по метаданным."

    has_docs = source not in ("none",)
    cust_total_fmt = f"{cust['total_volume']:,.0f} ₽".replace(",", " ") if cust["total_volume"] else "нет данных"

    prompt = SUMMARY_PROMPT.format(
        title=tender.title,
        nmck=f"{tender.nmck:,.0f} ₽".replace(",", " ") if tender.nmck else "не указана",
        days_left=f"{days_left}" if days_left is not None else "не указан",
        region=tender.region or "не указан",
        okpd_names=okved_to_text(tender.okpd_codes or []) or "не указан",
        law_type=tender.law_type or "не указан",
        bid_security=bid_security,
        contract_security=contract_security,
        customer_name=cust["name"] or "не указан",
        customer_inn=cust["inn"] or "не указан",
        customer_region=cust["region"] or "не указан",
        customer_okved=cust["okved_main"] or "не указан",
        customer_tender_count=cust["tender_count"],
        customer_total_volume=cust_total_fmt,
        docs_section=docs_section,
    )

    model_name = "gpt-4o-mini"
    client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL or None)

    start_ns = time.monotonic_ns()
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2800,
        temperature=0.3,
    )
    duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    gpt = json.loads(raw)

    verdict_raw = gpt.get("verdict", "изучить")
    urgency_raw = gpt.get("urgency", "нормально")

    key_risks = gpt.get("key_risks") or {}
    financial_risks = key_risks.get("financial_risks") or []
    contract_pct = tender.contract_security_percent
    if contract_pct is not None:
        has_flag = any("обеспечен" in f.lower() for f in financial_risks)
        if contract_pct > 15 and not has_flag:
            financial_risks.append(f"Обеспечение контракта {contract_pct}% (выше 15%)")
        elif contract_pct <= 15:
            financial_risks = [f for f in financial_risks if "обеспечен" not in f.lower()]

    customer_analysis = gpt.get("customer_analysis") or {}
    work_description = gpt.get("work_description") or {}
    required_documents = gpt.get("required_documents") or {}

    summary = {
        "version": 2,
        "customer_analysis": {
            "name": cust["name"], "inn": cust["inn"], "region": cust["region"],
            "okved_main": cust["okved_main"], "tender_count": cust["tender_count"],
            "total_volume": cust["total_volume"],
            "notes": customer_analysis.get("notes") or [],
        },
        "work_description": {
            "essence": work_description.get("essence", ""),
            "payment_terms": work_description.get("payment_terms"),
            "execution_period": work_description.get("execution_period"),
            "experience_requirements": work_description.get("experience_requirements") or [],
            "deadline_info": work_description.get("deadline_info"),
        },
        "key_risks": {
            "certifications": key_risks.get("certifications") or [],
            "financial_risks": financial_risks,
            "technical_risks": key_risks.get("technical_risks") or [],
            "unusual_conditions": key_risks.get("unusual_conditions") or [],
        },
        "required_documents": {
            "mandatory": required_documents.get("mandatory") or [],
            "optional": required_documents.get("optional") or [],
            "special_forms": required_documents.get("special_forms") or [],
        },
        "verdict": VERDICT_MAP.get(verdict_raw, verdict_raw),
        "verdict_reason": gpt.get("verdict_reason", ""),
        "tender_type": gpt.get("tender_type", "другое"),
        "has_docs": has_docs,
        "days_left": days_left,
        "urgency": URGENCY_MAP.get(urgency_raw, urgency_raw),
    }

    usage = response.usage
    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0
    cost = calculate_cost(model_name, input_tokens, output_tokens)

    return {
        "summary": summary,
        "metrics": {
            "strategy": strategy,
            "model": model_name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
            "duration_ms": duration_ms,
            "was_truncated": was_truncated,
            "truncated_reason": truncated_reason,
            "original_total_tokens": original_total_tokens,
        },
    }


def run_experiment_batch(
    experiment: "Experiment",
    output_path: str | None = None,
    stdout=None,
) -> None:
    from tqdm import tqdm
    from apps.documents.models import TenderDocument
    from .models import Experiment, PromptTemplate, SummaryExperiment

    experiment.status = Experiment.Status.RUNNING
    experiment.save(update_fields=["status"])

    tenders = list(
        Tender.objects.select_related("customer")
        .filter(id__in=experiment.tender_ids)
    )
    tender_map = {t.id: t for t in tenders}
    tenders = [tender_map[tid] for tid in experiment.tender_ids if tid in tender_map]

    variants = experiment.variants
    stats: dict[str, list[dict]] = {v["label"]: [] for v in variants}
    errors = 0
    f = None

    try:
        if output_path:
            f = open(output_path, "w", encoding="utf-8")
            _write_experiment_header(f, experiment, tenders, variants)

        total = len(tenders) * len(variants)
        progress = tqdm(total=total, desc="Experiment runs")

        for tender in tenders:
            docs = list(
                TenderDocument.objects.filter(
                    tender=tender,
                    parse_status=TenderDocument.ParseStatus.DONE,
                    is_scanned=False,
                ).exclude(parsed_text="").order_by("content_priority", "filename")
            )

            if f:
                _write_tender_block(f, tender, docs)

            for variant in variants:
                label = variant["label"]
                if f:
                    f.write(f"\n{'─' * 64}\n")
                    f.write(f"[{label}] {variant['name']}\n")
                    f.write(f"{'─' * 64}\n")

                try:
                    result = generate_summary_with_variant(tender, variant)
                    metrics = result["metrics"]

                    pt = PromptTemplate.objects.filter(
                        id=metrics.get("prompt_template_id"),
                    ).first()

                    SummaryExperiment.objects.create(
                        tender=tender,
                        experiment=experiment,
                        variant_label=label,
                        variant_name=variant["name"],
                        strategy=metrics["strategy"],
                        model=metrics["model"],
                        actual_model=metrics.get("actual_model", ""),
                        prompt_template=pt,
                        params=variant.get("params", {}),
                        input_tokens=metrics["input_tokens"],
                        output_tokens=metrics["output_tokens"],
                        cost_usd=metrics["cost_usd"],
                        duration_ms=metrics["duration_ms"],
                        was_truncated=metrics["was_truncated"],
                        truncated_reason=metrics["truncated_reason"],
                        original_total_tokens=metrics["original_total_tokens"],
                        result=result["summary"],
                    )

                    stats[label].append(metrics)

                    if f:
                        _write_run_metrics(f, metrics)
                        f.write("\nРезультат:\n")
                        f.write(json.dumps(result["summary"], indent=2, ensure_ascii=False))
                        f.write("\n")

                except Exception as exc:
                    errors += 1
                    if f:
                        f.write(f"\nОШИБКА: {exc}\n")
                    if stdout:
                        stdout.write(f"  Error {tender.number} [{label}]: {exc}\n")
                    logger.exception("Experiment run failed: tender=%d variant=%s", tender.id, label)

                progress.update(1)

            if f:
                f.write("\n")
                f.flush()

        progress.close()

        if f:
            _write_experiment_summary(f, experiment, stats, errors)

    finally:
        if f:
            f.close()

    experiment.status = Experiment.Status.COMPLETED
    experiment.completed_at = timezone.now()
    experiment.save(update_fields=["status", "completed_at"])


def _write_experiment_header(f, experiment, tenders, variants) -> None:
    now = timezone.now()
    f.write(f"{'=' * 64}\n")
    f.write(f"ЭКСПЕРИМЕНТ: {experiment.name}\n")
    f.write(f"Запущен: {now.strftime('%d %B %Y, %H:%M')}\n")
    if experiment.description:
        f.write(f"Описание: {experiment.description}\n")
    f.write(f"{'=' * 64}\n\n")

    f.write("ВАРИАНТЫ:\n\n")
    for v in variants:
        f.write(f"[{v['label']}] {v['name']}\n")
        f.write(f"    Стратегия: {v.get('strategy', '—')}\n")
        f.write(f"    Модель: {v.get('model', '—')}\n")
        f.write(f"    Промпт: {v.get('prompt_template', '—')}\n")
        f.write("\n")

    f.write(f"Тендеров: {len(tenders)}\n\n")


def _write_tender_block(f, tender: Tender, docs) -> None:
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
        f.write(f"Дедлайн: {tender.deadline_at.strftime('%d %B %Y')}\n")

    f.write("\nДокументы:\n")
    total_chars = 0
    for d in docs:
        chars = len(d.parsed_text) if d.parsed_text else 0
        total_chars += chars
        f.write(f"  - {d.filename} (priority={d.content_priority}, {chars:,} символов)\n".replace(",", " "))
    f.write(f"Всего символов: {total_chars:,}\n".replace(",", " "))


def _write_run_metrics(f, metrics: dict) -> None:
    f.write("Метрики:\n")
    f.write(f"  Токены: {metrics['input_tokens']:,} / {metrics['output_tokens']:,} (вход / выход)\n".replace(",", " "))
    f.write(f"  Стоимость: ${float(metrics['cost_usd']):.4f}\n")
    f.write(f"  Время: {metrics['duration_ms'] / 1000:.1f} сек\n")
    actual = metrics.get("actual_model", "")
    if actual and actual != metrics.get("model", ""):
        f.write(f"  Модель API: {actual}\n")
    if metrics.get("was_truncated"):
        f.write(f"  Усечение: ДА, {metrics['truncated_reason']}\n")
    else:
        f.write("  Усечение: нет\n")


def _write_experiment_summary(f, experiment, stats: dict, errors: int) -> None:
    f.write(f"\n{'=' * 64}\n")
    f.write("СВОДКА ЭКСПЕРИМЕНТА\n")
    f.write(f"{'=' * 64}\n")
    f.write(f"Завершён: {timezone.now().strftime('%d %B %Y, %H:%M')}\n")

    total_runs = sum(len(v) for v in stats.values())
    f.write(f"Всего запусков: {total_runs}\n")
    if errors:
        f.write(f"Ошибок: {errors}\n")

    labels_with_data = [label for label, runs in stats.items() if runs]
    if not labels_with_data:
        return

    for label in labels_with_data:
        runs = stats[label]
        truncated = sum(1 for m in runs if m.get("was_truncated"))
        if truncated:
            f.write(f"Усечений [{label}]: {truncated} из {len(runs)}\n")

    f.write("\nСредние метрики:\n")
    col_w = 20
    header = "".ljust(col_w)
    for label in labels_with_data:
        variant_name = label
        for v in experiment.variants:
            if v["label"] == label:
                variant_name = f"[{label}] {v['name']}"
                break
        header += variant_name.ljust(col_w)
    f.write(header + "\n")

    rows = [
        ("Входные токены", "input_tokens"),
        ("Выходные токены", "output_tokens"),
        ("Стоимость", "cost_usd"),
        ("Время", "duration_ms"),
    ]

    for row_label, key in rows:
        parts = [row_label.ljust(col_w)]
        for label in labels_with_data:
            vals = [float(m[key]) for m in stats[label]]
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


def _nonempty(value: Any) -> bool:
    """True если значение непустое (не None, не '', не [])."""
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, list) and not value:
        return False
    return True


def upsert_tender(data: dict[str, Any]) -> Tender:
    """Создать или обновить тендер из сырых данных парсера."""
    customer = None
    inn = data.get("customer_inn", "").strip()
    name = data.get("customer_name", "").strip()
    if inn:
        customer, _ = Customer.objects.get_or_create(
            inn=inn,
            defaults={
                "name": name,
                "full_name": data.get("customer_full_name", ""),
                "region": data.get("customer_region", data.get("region", "")),
            },
        )
    elif name:
        customer = Customer.objects.filter(inn="", name=name).first()
        if not customer:
            customer = Customer.objects.create(
                inn="", name=name, region=data.get("customer_region", "")
            )

    # If enrichment brought INN for an existing tender, update the old Customer
    number = data.get("number", "")
    if inn and number:
        existing_tender = Tender.objects.filter(number=number).select_related("customer").first()
        if existing_tender and existing_tender.customer and not existing_tender.customer.inn:
            old_customer = existing_tender.customer
            old_customer.inn = inn
            old_customer.full_name = data.get("customer_full_name", "") or old_customer.full_name
            old_customer.region = data.get("customer_region", data.get("region", "")) or old_customer.region
            old_customer.save(update_fields=["inn", "full_name", "region"])
            customer = old_customer

    source_url = data.get("source_url", "")
    procedure_type = data.get("procedure_type") or detect_procedure_type(source_url)
    source = data.get("source", Tender.Source.EIS)

    always_update = {
        "source": source,
        "title": data.get("title", ""),
        "customer": customer,
        "status": data.get("status", Tender.Status.ACTIVE),
        "law_type": data.get("law_type", ""),
        "procedure_type": procedure_type,
        "source_url": source_url,
        "raw_json": data,
    }

    enrichment_fields = {
        "nmck": data.get("nmck"),
        "region": data.get("region", ""),
        "okpd_codes": data.get("okpd_codes", []),
        "published_at": data.get("published_at"),
        "deadline_at": data.get("deadline_at"),
        "auction_date": data.get("auction_date"),
        "trading_platform": data.get("trading_platform", ""),
        "trading_platform_url": data.get("trading_platform_url", ""),
        "bid_security_amount": data.get("bid_security_amount"),
        "bid_security_required": data.get("bid_security_required"),
        "contract_security_amount": data.get("contract_security_amount"),
        "contract_security_percent": data.get("contract_security_percent"),
    }

    existing = Tender.objects.filter(number=data["number"], source=source).first()

    if existing:
        safe_enrichment = {
            k: v for k, v in enrichment_fields.items()
            if _nonempty(v) or not _nonempty(getattr(existing, k))
        }
        defaults = {**always_update, **safe_enrichment}
    else:
        defaults = {**always_update, **enrichment_fields}

    tender, created = Tender.objects.update_or_create(
        number=data["number"],
        source=source,
        defaults=defaults,
    )
    return tender
