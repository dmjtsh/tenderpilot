import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

from django.utils import timezone

from apps.tenders.models import Tender, TenderSummaryV2
from apps.tenders.services import calculate_cost
from apps.tenders.summary_v2.context import get_step_context

logger = logging.getLogger(__name__)

VALID_STEPS = {"financial", "timeline", "requirements", "work", "risks", "customer"}
PARALLEL_STEPS = ["financial", "timeline", "requirements", "work", "customer"]


def generate_step(tender_id: int, step: str, model: str = "deepseek-chat") -> dict:
    if step not in VALID_STEPS:
        raise ValueError(f"Unknown step: {step}. Valid: {VALID_STEPS}")

    tender = Tender.objects.select_related("customer").get(pk=tender_id)
    ctx = get_step_context(tender, step)

    if ctx["source"] == "none":
        raise ValueError(f"No documents for tender {tender_id}")

    data = _run_step(tender, step, ctx["context"], model)
    return data


def _run_step(tender: Tender, step: str, context: str, model: str) -> dict:
    if step == "financial":
        from apps.tenders.summary_v2.prompts.financial import analyze_financial
        return analyze_financial(tender, context, model=model)
    if step == "timeline":
        from apps.tenders.summary_v2.prompts.timeline import analyze_timeline
        return analyze_timeline(tender, context, model=model)
    if step == "requirements":
        from apps.tenders.summary_v2.prompts.requirements import analyze_requirements
        return analyze_requirements(tender, context, model=model)
    if step == "work":
        from apps.tenders.summary_v2.prompts.work import analyze_work
        return analyze_work(tender, context, model=model)
    if step == "risks":
        from apps.tenders.summary_v2.prompts.risks import analyze_risks
        return analyze_risks(tender, context, model=model)
    if step == "customer":
        from apps.tenders.summary_v2.prompts.customer import analyze_customer
        return analyze_customer(tender, context, model=model)
    raise ValueError(f"Unknown step: {step}")


def generate_step_with_metrics(
    tender: Tender,
    step: str,
    model: str = "deepseek-chat",
) -> dict:
    """A/B-совместимый формат: {summary, metrics}."""
    ctx = get_step_context(tender, step)

    if ctx["source"] == "none":
        raise ValueError(f"No documents for tender {tender.id}")

    data = _run_step(tender, step, ctx["context"], model)

    metrics = data["metrics"]
    cost = calculate_cost(
        metrics["model"],
        metrics["input_tokens"],
        metrics["output_tokens"],
    )

    return {
        "summary": data["result"],
        "metrics": {
            "strategy": f"v2_{step}",
            "model": metrics["model"],
            "actual_model": metrics["actual_model"],
            "prompt_template": f"v2_{step}_builtin",
            "prompt_template_id": None,
            "input_tokens": metrics["input_tokens"],
            "output_tokens": metrics["output_tokens"],
            "cost_usd": cost,
            "duration_ms": metrics["duration_ms"],
            "was_truncated": ctx.get("was_truncated", False),
            "truncated_reason": ctx.get("truncated_reason", ""),
            "original_total_tokens": ctx.get("original_total_tokens", 0),
        },
    }


def generate_tender_summary_v2(
    tender_id: int,
    model: str = "deepseek-chat",
) -> TenderSummaryV2:
    start_ns = time.monotonic_ns()
    tender = Tender.objects.select_related("customer").get(pk=tender_id)

    contexts = {}
    for step in VALID_STEPS:
        contexts[step] = get_step_context(tender, step)

    has_docs = any(ctx["source"] != "none" for ctx in contexts.values())
    if not has_docs:
        raise ValueError(f"No documents for tender {tender_id}")

    step_results: dict[str, dict | None] = {}
    step_metrics: dict[str, dict] = {}

    def _run_single(step: str) -> tuple[str, dict]:
        ctx = contexts[step]
        if ctx["source"] == "none":
            return step, {"result": None, "metrics": None}
        return step, _run_step(tender, step, ctx["context"], model)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_run_single, s): s for s in PARALLEL_STEPS}
        for future in as_completed(futures):
            step_name = futures[future]
            try:
                _, data = future.result(timeout=60)
                step_results[step_name] = data.get("result")
                if data.get("metrics"):
                    step_metrics[step_name] = data["metrics"]
            except Exception:
                logger.exception("Step %s failed for tender %s", step_name, tender_id)
                step_results[step_name] = None

    prior_analysis = {k: v for k, v in step_results.items() if v is not None}

    risks_ctx = contexts["risks"]
    if risks_ctx["source"] != "none":
        try:
            from apps.tenders.summary_v2.prompts.risks import analyze_risks
            risks_data = analyze_risks(
                tender, risks_ctx["context"], model=model,
                prior_analysis=prior_analysis,
            )
            step_results["risks"] = risks_data["result"]
            step_metrics["risks"] = risks_data["metrics"]
        except Exception:
            logger.exception("Risks step failed for tender %s", tender_id)
            step_results["risks"] = None

    total_duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
    total_input = sum(m.get("input_tokens", 0) for m in step_metrics.values())
    total_output = sum(m.get("output_tokens", 0) for m in step_metrics.values())
    total_cost = sum(
        calculate_cost(m["model"], m.get("input_tokens", 0), m.get("output_tokens", 0))
        for m in step_metrics.values()
    )

    summary = {
        "version": "v2",
        "generated_at": timezone.now().isoformat(),
        "general": {
            "title": tender.title,
            "customer_name": tender.customer.name if tender.customer else None,
            "customer_inn": tender.customer.inn if tender.customer else None,
            "law_type": tender.law_type,
            "nmck": float(tender.nmck) if tender.nmck else None,
            "region": tender.region,
        },
        "customer_analysis": step_results.get("customer"),
        "work_description": step_results.get("work"),
        "financial": step_results.get("financial"),
        "timeline": step_results.get("timeline"),
        "requirements": step_results.get("requirements"),
        "risks": step_results.get("risks"),
    }

    obj, _ = TenderSummaryV2.objects.update_or_create(
        tender=tender,
        defaults={
            "summary": summary,
            "step_metrics": step_metrics,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cost_usd": Decimal(str(round(total_cost, 4))),
            "generation_time_ms": total_duration_ms,
            "model": model,
        },
    )

    return obj
