#!/usr/bin/env python3
"""
Скачивает все документы тендера по ссылке с zakupki.gov.ru.
Использование:
  python3 download_tender.py "<URL>"
  python3 download_tender.py "https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=0273100001126000204"
"""
import json
import os
import re
import sys

import requests
from lxml import etree

import docs_fetcher


def sanitize(name: str, max_len: int = 80) -> str:
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:max_len]


def parse_url(url: str) -> tuple[str, str]:
    m = re.search(r'regNumber=(\w+)', url)
    if not m:
        print(f"Ошибка: не найден regNumber в URL: {url}")
        sys.exit(1)
    purchase_number = m.group(1)
    law_type = "223-ФЗ" if ("notice223" in url or "noticeInfoId" in url) else "44-ФЗ"
    return purchase_number, law_type


def get_notice_info_id(url: str) -> str | None:
    m = re.search(r'noticeInfoId=(\d+)', url)
    return m.group(1) if m else None


def _get_tree(purchase_number: str, fallback_url: str):
    """Скачивает страницу тендера, следует редиректу, возвращает (tree, final_url)."""
    try:
        resp = requests.get(
            f"http://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber={purchase_number}",
            headers=docs_fetcher.HEADERS, timeout=20, allow_redirects=True,
        )
        page_url = resp.url
    except Exception:
        page_url = fallback_url
    resp = requests.get(page_url, headers=docs_fetcher.HEADERS, timeout=30)
    resp.raise_for_status()
    parser = etree.HTMLParser()
    return etree.fromstring(resp.content, parser), page_url


def _field_after(tree, label: str) -> str:
    """Возвращает текст следующего sibling-элемента после элемента с нужным текстом."""
    for el in tree.xpath(f'//*[normalize-space(text())="{label}"]'):
        parent = el.getparent()
        if parent is None:
            continue
        children = list(parent)
        try:
            idx = children.index(el)
        except ValueError:
            continue
        for sibling in children[idx + 1:]:
            texts = [t.strip() for t in sibling.xpath('.//text()') if t.strip()]
            val = " ".join(t for t in texts if not t.startswith('$('))
            if val:
                return val
    return ""


def _parse_price(s: str) -> float | None:
    """'191 800,00 ₽' → 191800.0"""
    cleaned = re.sub(r'[^\d,.]', '', s).replace(',', '.')
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _parse_date(s: str) -> str:
    """'25.04.2026 23:45' → '2026-04-25T23:45' или '2026-04-25'"""
    s = s.strip().split('(')[0].strip()  # убираем "(МСК+9)"
    m = re.match(r'(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{2}:\d{2}))?', s)
    if not m:
        return s
    d, mo, y, t = m.groups()
    return f"{y}-{mo}-{d}T{t}" if t else f"{y}-{mo}-{d}"


def fetch_tender_json(url: str, purchase_number: str, law_type: str = "44-ФЗ") -> dict:
    """Парсит страницу тендера и возвращает нормализованный JSON-словарь."""
    try:
        tree, _ = _get_tree(purchase_number, url)
    except Exception as e:
        return {"error": str(e), "purchase_number": purchase_number}

    f = lambda label: _field_after(tree, label)

    # --- Основное ---
    result = {
        "purchase_number": purchase_number,
        "law": law_type,
        "procedure": f("Способ определения поставщика (подрядчика, исполнителя)"),
        "stage": f("Этап закупки"),
        "name": f("Наименование объекта закупки"),
        "ikz": f("Идентификационный код закупки (ИКЗ)"),
        "platform": f("Наименование электронной площадки в информационно-телекоммуникационной сети «Интернет»"),
    }

    # Цена
    # Цена — ищем непосредственно числовое значение в блоке НМЦ
    price_raw = ""
    for el in tree.xpath('//*[contains(@class,"price-block__value")]'):
        t = " ".join(s.strip() for s in el.xpath('.//text()') if s.strip())
        if t and any(c.isdigit() for c in t):
            price_raw = t
            break
    if not price_raw:
        price_raw = f("Начальная (максимальная) цена контракта")
    # Обрезаем до первого числа с валютой
    m_price = re.search(r'[\d\s]+[,.][\d]+', price_raw)
    result["price"] = _parse_price(m_price.group(0) if m_price else price_raw)
    result["price_str"] = (m_price.group(0).strip() if m_price else price_raw) + " ₽"

    # --- Заказчик ---
    result["customer"] = {
        "name": f("Организация, осуществляющая размещение"),
        "address": f("Почтовый адрес"),
        "contact": f("Ответственное должностное лицо"),
        "email": f("Адрес электронной почты"),
        "phone": f("Номер контактного телефона"),
        "region": f("Регион"),
    }

    # --- Даты ---
    result["dates"] = {
        "published": _parse_date(f("Размещено")) if f("Размещено") else None,
        "submission_start": _parse_date(f("Дата и время начала срока подачи заявок")) if f("Дата и время начала срока подачи заявок") else None,
        "submission_end": _parse_date(f("Дата и время окончания срока подачи заявок")) if f("Дата и время окончания срока подачи заявок") else None,
        "auction": _parse_date(f("Дата проведения процедуры подачи предложений о цене контракта либо о сумме цен единиц товара, работы, услуги")) if f("Дата проведения процедуры подачи предложений о цене контракта либо о сумме цен единиц товара, работы, услуги") else None,
        "results": _parse_date(f("Дата подведения итогов определения поставщика (подрядчика, исполнителя)")) if f("Дата подведения итогов определения поставщика (подрядчика, исполнителя)") else None,
        "contract_start": f("Дата начала исполнения контракта"),
        "contract_end": _parse_date(f("Срок исполнения контракта")) if f("Срок исполнения контракта") else None,
    }

    # --- Обеспечение ---
    bid_str = f("Размер обеспечения заявки")
    exec_str = f("Размер обеспечения исполнения контракта")
    result["security"] = {
        "bid_required": f("Требуется обеспечение заявки") == "Да",
        "bid_amount": _parse_price(bid_str),
        "bid_amount_str": bid_str,
        "execution_required": f("Требуется обеспечение исполнения контракта") == "Да",
        "execution_str": exec_str,
    }

    # --- Гарантия ---
    result["warranty"] = f("Срок, на который предоставляется гарантия и (или) требования к объему предоставления гарантий качества товара, работы, услуги")

    # --- Место исполнения ---
    result["delivery_address"] = f("Место поставки товара, выполнения работы или оказания услуги")

    # --- Позиции объекта закупки ---
    items = []
    for row in tree.xpath('//*[contains(@class,"tableBlock__row") or contains(@class,"lots-position")]'):
        # ОКПД2-код в первой ячейке
        cells = row.xpath('.//*[contains(@class,"col") or self::td]')
        if len(cells) < 3:
            continue
        texts = [" ".join(t.strip() for t in c.xpath('.//text()') if t.strip()) for c in cells]
        texts = [t for t in texts if t]
        if not texts or not re.match(r'\d{2}\.\d{2}', texts[0]):
            continue
        # ОКПД2 — берём только первый код (до пробела)
        okpd2 = re.match(r'[\d.]+', texts[0]).group(0).rstrip('.')
        item = {"okpd2": okpd2}
        if len(texts) > 1:
            item["name"] = texts[1]
        if len(texts) > 2:
            item["unit"] = texts[2]
        if len(texts) > 3:
            item["quantity"] = _parse_price(texts[3])
        if len(texts) > 4:
            item["unit_price"] = _parse_price(texts[4])
        if len(texts) > 5:
            item["total"] = _parse_price(texts[5])
        items.append(item)
    result["items"] = items

    # --- Требования к участникам ---
    req_el = tree.xpath('//*[contains(@class,"requirements_participants")]')
    if req_el:
        reqs = _clean_texts(req_el[0].xpath('.//text()'))
        result["requirements"] = reqs
    else:
        result["requirements"] = []

    return result


def fetch_tender_info(url: str, purchase_number: str) -> str:
    """Скачивает страницу тендера и извлекает полный структурированный текст."""
    try:
        tree, _ = _get_tree(purchase_number, url)
    except Exception as e:
        return f"Не удалось загрузить страницу: {e}"

    # Удаляем навигацию, скрипты, стили, футер — всё лишнее
    for tag in tree.xpath('//script | //style | //nav | //footer | //header | //*[@class and (contains(@class,"breadcrumb") or contains(@class,"topline") or contains(@class,"menu") or contains(@class,"footer") or contains(@class,"navbar"))]'):
        tag.getparent().remove(tag)

    # Главный контент — блоки blockInfo и cardMainInfo
    output_sections = []

    # 1. Шапка с основными реквизитами
    header = tree.xpath('//*[contains(@class,"cardMainInfo")]')
    if header:
        texts = _clean_texts(header[0].xpath('.//text()'))
        if texts:
            output_sections.append("=== ОСНОВНАЯ ИНФОРМАЦИЯ ===\n" + _format_texts(texts, pair=False))

    # 2. Все секции blockInfo — только верхнего уровня (не вложенные)
    seen = set()
    for block in tree.xpath('//*[contains(@class,"blockInfo")]'):
        # Пропускаем блоки, которые являются дочерними другого blockInfo
        parent_has_blockinfo = any(
            "blockInfo" in (a.get("class") or "")
            for a in block.iterancestors()
            if a.get("class")
        )
        if parent_has_blockinfo:
            continue

        block_id = id(block)
        if block_id in seen:
            continue
        seen.add(block_id)

        # Заголовок секции
        title_els = block.xpath('.//*[contains(@class,"blockInfo__title")]')
        title = ""
        if title_els:
            title = " ".join(_clean_texts(title_els[0].xpath('.//text()')))

        # Весь текст секции
        all_texts = _clean_texts(block.xpath('.//text()'))
        # Убираем заголовок из текста чтобы не дублировать
        if title:
            all_texts = [t for t in all_texts if t != title]

        if not all_texts:
            continue

        header_line = f"=== {title.upper()} ===" if title else "==="
        output_sections.append(header_line + "\n" + _format_texts(all_texts, pair=False))

    return "\n\n".join(output_sections)


_NAV_JUNK = {
    "позиция ктру", "позиция плана-графика", "контракт", "жалоба",
    "внеплановая проверка", "ктру", "история", "связанные закупки",
}


def _clean_texts(raw_texts) -> list[str]:
    """Убирает JS, навигационный мусор, нормализует пробелы."""
    import re as _re
    result = []
    for t in raw_texts:
        t = _re.sub(r'\s+', ' ', t).strip()
        if not t or len(t) < 2:
            continue
        if t.startswith('$(') or t.startswith('var ') or t.startswith('function'):
            continue
        if t.lower() in _NAV_JUNK:
            continue
        result.append(t)
    return result


def _format_texts(texts: list[str], pair: bool = True) -> str:
    """Выводит тексты построчно. pair=True — пробует объединять метку со значением."""
    if not pair:
        return "\n".join(f"  {t}" for t in texts)

    lines = []
    i = 0
    while i < len(texts):
        t = texts[i]
        next_t = texts[i + 1] if i + 1 < len(texts) else None
        # Пара метка:значение — только если метка похожа на подпись поля
        # (короткая, не число, не заканчивается на цифру или запятую)
        if (next_t
                and len(t) < 100
                and not t[-1].isdigit()
                and t[-1] not in ".,₽%"
                and not t[0].isdigit()):
            lines.append(f"  {t}: {next_t}")
            i += 2
        else:
            lines.append(f"  {t}")
            i += 1
    return "\n".join(lines)


def download_all(url: str, output_root: str = "tenders"):
    purchase_number, law_type = parse_url(url)
    notice_info_id = get_notice_info_id(url)

    print(f"Тендер:  {purchase_number} ({law_type})")

    # Папка назначения
    dest = os.path.join(output_root, sanitize(purchase_number))
    os.makedirs(dest, exist_ok=True)
    print(f"Папка:   {dest}\n")

    # Скачиваем и сохраняем info.txt + info.json
    print("Скачиваем информацию со страницы...")
    info_text = fetch_tender_info(url, purchase_number)
    with open(os.path.join(dest, "info.txt"), "w", encoding="utf-8") as f:
        f.write(f"Источник: {url}\n\n")
        f.write(info_text)
    print(f"  → info.txt ({len(info_text):,} символов)")

    data = fetch_tender_json(url, purchase_number, law_type)
    with open(os.path.join(dest, "info.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  → info.json ({len(data.get('items', []))} позиций объекта закупки)\n")

    # Список документов
    if "223" in law_type:
        if not notice_info_id:
            print("Ошибка: noticeInfoId не найден в URL для 223-ФЗ")
            sys.exit(1)
        doc_list = docs_fetcher._get_docs_223fz(notice_info_id)
    else:
        doc_list = docs_fetcher._get_docs_44fz(purchase_number)

    if not doc_list:
        print("Документы не найдены.")
        return

    print(f"Найдено документов: {len(doc_list)}")

    for i, doc in enumerate(doc_list, 1):
        name = doc["name"]
        file_url = doc["url"]

        ext = ""
        for candidate in [".pdf", ".docx", ".doc", ".xlsx", ".xls", ".zip", ".rar", ".sig"]:
            if candidate in name.lower() or candidate in file_url.lower():
                ext = candidate
                break

        safe_name = sanitize(name)
        if ext and not safe_name.lower().endswith(ext):
            safe_name += ext

        print(f"[{i}/{len(doc_list)}] {name[:70]}")
        content, _ = docs_fetcher._download_file(file_url)

        if not content:
            print("  → не удалось скачать")
            continue

        if not ext:
            if content[:4] == b"%PDF":
                safe_name += ".pdf"
            elif content[:4] == b"Rar!":
                safe_name += ".rar"
            elif content[:4] == b"PK\x03\x04":
                safe_name += ".docx"

        # Переопределяем расширение если содержимое ZIP — Excel
        if content[:4] == b"PK\x03\x04" and safe_name.lower().endswith(".docx"):
            import zipfile as _zf, io as _io
            try:
                with _zf.ZipFile(_io.BytesIO(content)) as zf:
                    names = zf.namelist()
                    if any(n.startswith("xl/") for n in names):
                        safe_name = safe_name[:-5] + ".xlsx"
            except Exception:
                pass

        filepath = os.path.join(dest, safe_name)
        if os.path.exists(filepath):
            base, ext2 = os.path.splitext(filepath)
            filepath = f"{base}_{i}{ext2}"

        with open(filepath, "wb") as f:
            f.write(content)

        # Извлекаем текст и сохраняем рядом как .txt
        txt_path = filepath + ".txt"
        text = docs_fetcher._extract_from_bytes(content, os.path.basename(filepath))
        if text and len(text) > 50:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"  → {os.path.basename(filepath)} ({len(content):,} байт) + .txt ({len(text):,} символов)")
        else:
            print(f"  → {os.path.basename(filepath)} ({len(content):,} байт) [текст не извлечён]")

    print(f"\nГотово. Открыть папку:")
    print(f"  open \"{os.path.abspath(dest)}\"")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    download_all(sys.argv[1])
