#!/usr/bin/env python3
"""
Оффлайн-скрипт: дедупликация xlsx TenderGuru → чистый CSV для outreach.

Запуск:
    python scripts/prepare_outreach_list.py \
        --xlsx "~/Downloads/tenderGuru_ru_example_contracts (1).xlsx" \
        --output outreach_list.csv
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import List

try:
    import pandas as pd
except ImportError:
    sys.exit("Установи pandas: pip install pandas openpyxl")


def _clean_emails(raw: str) -> list[str]:
    if not isinstance(raw, str) or not raw.strip():
        return []
    emails = []
    for part in re.split(r"[\n,;]+", raw):
        part = part.strip()
        match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", part)
        if match:
            emails.append(match.group(0).lower())
    return list(dict.fromkeys(emails))  # unique, order preserved


def _clean_phones(raw: str) -> list[str]:
    if not isinstance(raw, str) or not raw.strip():
        return []
    phones = []
    for part in re.split(r"\n", raw):
        part = part.strip()
        if part:
            phones.append(part)
    return list(dict.fromkeys(phones))


def _clean_codes(raw) -> list[str]:
    if not isinstance(raw, str) or not raw.strip():
        return []
    return [c.strip() for c in raw.split() if re.match(r"^\d{2}\.", c.strip())]


def _safe_str(val) -> str:
    if pd.isna(val) if not isinstance(val, str) else False:
        return ""
    return str(val).strip()


def prepare(xlsx_path: str, output_path: str) -> None:
    print(f"Читаем {xlsx_path} ...")
    df = pd.read_excel(xlsx_path, sheet_name="Контракты", dtype=str)
    df.fillna("", inplace=True)

    print(f"Строк в xlsx: {len(df)}")

    # Нормализуем ИНН: убираем пробелы, невалидные строки
    df["inn_clean"] = df["ИНН поставщика"].str.strip()
    df = df[df["inn_clean"].str.match(r"^\d{10,12}$")]
    print(f"Строк с валидным ИНН: {len(df)}")

    rows = []
    for inn, group in df.groupby("inn_clean", sort=False):
        first = group.iloc[0]

        all_emails: list[str] = []
        all_phones: list[str] = []
        won_products: list[str] = []
        okpd_codes: list[str] = []

        for _, row in group.iterrows():
            all_emails.extend(_clean_emails(row["E-mail"]))
            all_phones.extend(_clean_phones(row["Телефон"]))
            product = _safe_str(row["Закупаемая продукция"])
            if product and product not in won_products:
                won_products.append(product)
            okpd_codes.extend(_clean_codes(row["Коды"]))

        # Уникализация
        all_emails = list(dict.fromkeys(all_emails))
        all_phones = list(dict.fromkeys(all_phones))
        okpd_codes = list(dict.fromkeys(okpd_codes))

        if not all_emails:
            continue  # без email — нет смысла

        rows.append({
            "inn": inn,
            "company_name": _safe_str(first["Поставщик"]).replace(" -", "").strip(),
            "emails": "|".join(all_emails),
            "phones": "|".join(all_phones[:5]),
            "director": _safe_str(first["Руководитель поставшика"]),
            "won_products": json.dumps(won_products[:20], ensure_ascii=False),
            "okpd_codes": json.dumps(okpd_codes[:15], ensure_ascii=False),
            "region": _safe_str(first["Регион"]),
        })

    out_df = pd.DataFrame(rows)
    out_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"Готово: {len(out_df)} уникальных компаний → {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Дедупликация xlsx TenderGuru → CSV")
    parser.add_argument("--xlsx", required=True, help="Путь к xlsx-файлу")
    parser.add_argument("--output", default="outreach_list.csv", help="Выходной CSV")
    args = parser.parse_args()
    prepare(args.xlsx, args.output)


if __name__ == "__main__":
    main()
