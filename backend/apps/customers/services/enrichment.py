import logging
from datetime import timedelta

from django.utils import timezone

from apps.customers.models import CustomerProfile
from apps.customers.services.rusprofile import RusProfileParser
from apps.users.dadata import enrich_company_by_inn

logger = logging.getLogger(__name__)

RUSPROFILE_TTL_DAYS = 30
RUSPROFILE_RETRY_DAYS = 7


def _rusprofile_fresh(profile: CustomerProfile) -> bool:
    if not profile.rusprofile_updated_at:
        return False
    return profile.rusprofile_updated_at > timezone.now() - timedelta(days=RUSPROFILE_TTL_DAYS)


def _rusprofile_cooldown(profile: CustomerProfile) -> bool:
    """Не трогать если недавно упал."""
    if not profile.rusprofile_failed:
        return False
    if not profile.updated_at:
        return False
    return profile.updated_at > timezone.now() - timedelta(days=RUSPROFILE_RETRY_DAYS)


def enrich_customer(inn: str) -> CustomerProfile | None:
    if not inn or not inn.strip():
        return None

    inn = inn.strip()
    profile, _ = CustomerProfile.objects.get_or_create(inn=inn)

    # 1. DaData
    try:
        dadata_info = enrich_company_by_inn(inn)
        if dadata_info:
            profile.name = dadata_info["name"]
            profile.full_name = dadata_info["full_name"]
            profile.region = dadata_info["region"]
            profile.okved_main = dadata_info["okved_main"]
            profile.okved_list = dadata_info["okved_list"]
            profile.dadata_updated_at = timezone.now()
    except Exception as e:
        logger.warning("DaData failed for %s: %s", inn, e)

    # 2. RusProfile
    skip = _rusprofile_fresh(profile) or _rusprofile_cooldown(profile)
    if not skip:
        try:
            parser = RusProfileParser()
            rp = parser.get_company_info(inn)
            if rp:
                _apply_rusprofile_data(profile, rp)
                profile.rusprofile_updated_at = timezone.now()
                profile.rusprofile_failed = False
                profile.last_error = ""
            else:
                profile.rusprofile_failed = True
                profile.last_error = "No data returned"
        except Exception as e:
            logger.warning("RusProfile failed for %s: %s", inn, e)
            profile.rusprofile_failed = True
            profile.last_error = str(e)[:500]

    profile.save()
    return profile


def _apply_rusprofile_data(profile: CustomerProfile, data: dict) -> None:
    if data.get("director_name"):
        profile.director_name = data["director_name"]
    if data.get("status"):
        profile.status = data["status"]
    if data.get("founded_date"):
        profile.founded_date = data["founded_date"]
    if data.get("rusprofile_id"):
        profile.rusprofile_id = data["rusprofile_id"]

    # Финансы
    if data.get("revenue_rub") is not None:
        profile.revenue_rub = data["revenue_rub"]
    if data.get("profit_rub") is not None:
        profile.profit_rub = data["profit_rub"]
    if data.get("revenue_year") is not None:
        profile.revenue_year = data["revenue_year"]
    if data.get("employees_count") is not None:
        profile.employees_count = data["employees_count"]

    # Лицензии
    if data.get("licenses_count") is not None:
        profile.licenses_count = data["licenses_count"]
    if data.get("licenses_summary"):
        profile.licenses_summary = data["licenses_summary"]

    # Госзакупки
    if data.get("purchases_customer_count") is not None:
        profile.purchases_customer_count = data["purchases_customer_count"]
    if data.get("purchases_customer_amount") is not None:
        profile.purchases_customer_amount = data["purchases_customer_amount"]
    if data.get("purchases_supplier_count") is not None:
        profile.purchases_supplier_count = data["purchases_supplier_count"]

    # Риски
    if data.get("arbitration_count") is not None:
        profile.arbitration_count = data["arbitration_count"]
    if data.get("fssp_count") is not None:
        profile.fssp_count = data["fssp_count"]

    risk = {}
    if data.get("is_liquidated") is not None:
        risk["is_liquidated"] = data["is_liquidated"]
    if profile.arbitration_count and profile.arbitration_count > 0:
        risk["has_arbitration"] = True
    if profile.fssp_count and profile.fssp_count > 0:
        risk["has_fssp"] = True
    if risk:
        profile.risk_indicators = risk
