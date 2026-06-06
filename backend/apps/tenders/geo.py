"""
Гео-сортировка тендеров по близости к региону пользователя.

Справочник координат столиц 88+ регионов РФ + haversine distance.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from django.db.models import Case, FloatField, IntegerField, Value, When

from .region_aliases import REGION_ALIASES, _VARIANT_TO_CANONICAL, expand_regions

if TYPE_CHECKING:
    from django.db.models import QuerySet

# Координаты столиц регионов (lat, lon)
REGION_CAPITALS: dict[str, tuple[float, float]] = {
    # Республики
    "Адыгея": (44.6094, 40.1058),
    "Алтай": (51.9583, 85.9603),
    "Башкортостан": (54.7351, 55.9587),
    "Бурятия": (51.8340, 107.5845),
    "Дагестан": (42.9849, 47.5047),
    "Донецкая Народная Республика": (48.0028, 37.8053),
    "Ингушетия": (43.1682, 44.8142),
    "Кабардино-Балкария": (43.4854, 43.6073),
    "Калмыкия": (46.3078, 44.2558),
    "Карачаево-Черкесия": (44.2270, 42.0580),
    "Карелия": (61.7849, 34.3469),
    "Коми": (61.6685, 50.8352),
    "Крым": (44.9521, 34.1024),
    "Луганская Народная Республика": (48.5740, 39.3078),
    "Марий Эл": (56.6344, 47.8992),
    "Мордовия": (54.1871, 45.1749),
    "Саха (Якутия)": (62.0273, 129.7320),
    "Северная Осетия — Алания": (43.0244, 44.6816),
    "Татарстан": (55.7961, 49.1064),
    "Тыва": (51.7191, 94.4378),
    "Удмуртия": (56.8527, 53.2114),
    "Хакасия": (53.7214, 91.4428),
    "Чечня": (43.3177, 45.6946),
    "Чувашия": (56.1322, 47.2519),
    # Края
    "Алтайский край": (53.3481, 83.7798),
    "Забайкальский край": (52.0340, 113.5006),
    "Камчатский край": (53.0452, 158.6531),
    "Краснодарский край": (45.0353, 38.9753),
    "Красноярский край": (56.0090, 92.8725),
    "Пермский край": (58.0105, 56.2502),
    "Приморский край": (43.1332, 131.9113),
    "Ставропольский край": (45.0448, 43.9349),
    "Хабаровский край": (48.4827, 135.0684),
    # Области
    "Амурская область": (50.2907, 128.4947),
    "Архангельская область": (64.5401, 40.5433),
    "Астраханская область": (46.3497, 48.0408),
    "Белгородская область": (50.5955, 36.5873),
    "Брянская область": (53.2521, 34.3717),
    "Владимирская область": (56.1290, 40.4070),
    "Волгоградская область": (48.7080, 44.5133),
    "Вологодская область": (59.2204, 39.8918),
    "Воронежская область": (51.6720, 39.1843),
    "Запорожская область": (47.8388, 35.1396),
    "Ивановская область": (56.9966, 40.9715),
    "Иркутская область": (52.2855, 104.2890),
    "Калининградская область": (54.7065, 20.5110),
    "Калужская область": (54.5139, 36.2612),
    "Кемеровская область": (55.3548, 86.0883),
    "Кировская область": (58.6035, 49.6680),
    "Костромская область": (57.7676, 40.9269),
    "Курганская область": (55.4480, 65.3413),
    "Курская область": (51.7304, 36.1926),
    "Ленинградская область": (59.9343, 30.3351),
    "Липецкая область": (52.6100, 39.5947),
    "Магаданская область": (59.5682, 150.8086),
    "Московская область": (55.7558, 37.6173),
    "Мурманская область": (68.9585, 33.0827),
    "Нижегородская область": (56.3269, 44.0059),
    "Новгородская область": (58.5214, 31.2755),
    "Новосибирская область": (55.0302, 82.9204),
    "Омская область": (54.9893, 73.3682),
    "Оренбургская область": (51.7682, 55.0968),
    "Орловская область": (52.9685, 36.0692),
    "Пензенская область": (53.1950, 45.0184),
    "Псковская область": (57.8194, 28.3319),
    "Ростовская область": (47.2357, 39.7015),
    "Рязанская область": (54.6296, 39.7416),
    "Самарская область": (53.2001, 50.1500),
    "Саратовская область": (51.5330, 46.0344),
    "Сахалинская область": (46.9641, 142.7285),
    "Свердловская область": (56.8389, 60.6057),
    "Смоленская область": (54.7828, 32.0453),
    "Тамбовская область": (52.7212, 41.4523),
    "Тверская область": (56.8587, 35.9176),
    "Томская область": (56.4846, 84.9476),
    "Тульская область": (54.1930, 37.6174),
    "Тюменская область": (57.1522, 65.5272),
    "Ульяновская область": (54.3142, 48.4031),
    "Херсонская область": (46.6354, 32.6169),
    "Челябинская область": (55.1599, 61.4026),
    "Читинская область": (52.0340, 113.5006),
    "Ярославская область": (57.6261, 39.8845),
    # Города федерального значения
    "Москва": (55.7558, 37.6173),
    "Санкт-Петербург": (59.9343, 30.3351),
    "Севастополь": (44.6167, 33.5254),
    "Байконур": (45.6167, 63.3167),
    # Автономные округа и области
    "Еврейская АО": (48.7869, 132.9211),
    "Ненецкий АО": (67.6386, 53.0069),
    "Таймырский (Долгано-Ненецкий) АО": (69.3491, 88.2090),
    "Усть-Ордынский Бурятский АО": (52.8000, 104.7500),
    "Ханты-Мансийский АО — Югра": (61.0042, 69.0019),
    "Чукотский АО": (64.7352, 177.5148),
    "Ямало-Ненецкий АО": (66.5300, 66.6130),
}


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние между двумя точками в километрах."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_coords(region: str) -> tuple[float, float] | None:
    """Координаты столицы региона (по любому варианту написания)."""
    canonical = _VARIANT_TO_CANONICAL.get(region)
    if canonical:
        return REGION_CAPITALS.get(canonical)
    return REGION_CAPITALS.get(region)


def get_user_coords(user) -> tuple[float, float] | None:
    """Координаты из первого региона пользователя (profile.regions или directions)."""
    regions = get_user_regions(user)
    if not regions:
        return None
    return get_coords(regions[0])


def get_user_regions(user) -> list[str]:
    """Канонические регионы пользователя: сначала из CompanyProfile, fallback на directions."""
    from apps.users.models import CompanyProfile

    profiles = CompanyProfile.objects.filter(user=user)
    for profile in profiles:
        if profile.regions:
            return profile.regions
    for profile in profiles:
        for d in profile.directions.all():
            if d.regions:
                return list(d.regions)
    return []


def build_nearby_annotations(
    user_regions: list[str], user_coords: tuple[float, float]
) -> tuple[Case, Case]:
    """
    Возвращает (region_priority, geo_distance) annotations для ORM QuerySet.

    region_priority: 0 = свой регион, 1 = остальные
    geo_distance: расстояние в км до столицы региона тендера
    """
    expanded = set(expand_regions(user_regions))

    priority = Case(
        *[When(region=v, then=Value(0)) for v in expanded],
        default=Value(1),
        output_field=IntegerField(),
    )

    distance_whens: list[When] = []
    for canonical, coords in REGION_CAPITALS.items():
        dist = round(haversine(user_coords[0], user_coords[1], coords[0], coords[1]))
        aliases = REGION_ALIASES.get(canonical, [canonical])
        for alias in aliases:
            distance_whens.append(When(region=alias, then=Value(float(dist))))

    distance = Case(
        *distance_whens,
        default=Value(99999.0),
        output_field=FloatField(),
    )

    return priority, distance


def geo_sort_key(
    result: dict,
    expanded_regions: set[str],
    user_coords: tuple[float, float],
) -> tuple[int, float]:
    """Ключ сортировки для Python-списков результатов (Qdrant и пр.)."""
    region = result.get("region", "")
    is_own = 0 if region in expanded_regions else 1
    coords = get_coords(region)
    if coords and user_coords:
        dist = haversine(user_coords[0], user_coords[1], coords[0], coords[1])
    else:
        dist = 99999.0
    return (is_own, dist)
