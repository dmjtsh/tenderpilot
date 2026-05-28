import os
from datetime import date
from io import BytesIO
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from apps.tenders.summary_export import (
    _esc,
    _fmt_money,
    _register_fonts,
    _sections,
)

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
LOGO_PATH = os.path.join(FONT_DIR, "logo.png")

PAGE_W, PAGE_H = A4


def _styles():
    _register_fonts()
    base = getSampleStyleSheet()

    defs = [
        ParagraphStyle("OA_Brand", parent=base["Normal"],
                       fontName="DejaVuSans-Bold", fontSize=28, leading=32,
                       textColor=HexColor("#111827"), spaceAfter=2),
        ParagraphStyle("OA_Tagline", parent=base["Normal"],
                       fontName="DejaVuSans", fontSize=13, leading=18,
                       textColor=HexColor("#6B7280"), spaceAfter=20),
        ParagraphStyle("OA_CompanyLabel", parent=base["Normal"],
                       fontName="DejaVuSans", fontSize=9, leading=12,
                       textColor=HexColor("#9CA3AF"), spaceAfter=1),
        ParagraphStyle("OA_CompanyValue", parent=base["Normal"],
                       fontName="DejaVuSans-Bold", fontSize=11, leading=14,
                       textColor=HexColor("#111827"), spaceAfter=0),
        ParagraphStyle("OA_SummaryHeader", parent=base["Normal"],
                       fontName="DejaVuSans-Bold", fontSize=12, leading=15,
                       textColor=HexColor("#111827"), spaceBefore=20, spaceAfter=6),
        ParagraphStyle("OA_TenderNum", parent=base["Normal"],
                       fontName="DejaVuSans-Bold", fontSize=11, leading=14,
                       textColor=HexColor("#4F46E5"), spaceBefore=12, spaceAfter=4),
        ParagraphStyle("OA_TenderTitle", parent=base["Normal"],
                       fontName="DejaVuSans-Bold", fontSize=12, leading=15,
                       textColor=HexColor("#111827"), spaceBefore=8, spaceAfter=3),
        ParagraphStyle("OA_TenderMeta", parent=base["Normal"],
                       fontName="DejaVuSans", fontSize=9, leading=12,
                       textColor=HexColor("#6B7280"), spaceAfter=4),
        ParagraphStyle("OA_Section", parent=base["Normal"],
                       fontName="DejaVuSans-Bold", fontSize=11, leading=14,
                       textColor=HexColor("#1D4ED8"), spaceBefore=10, spaceAfter=4),
        ParagraphStyle("OA_Body", parent=base["Normal"],
                       fontName="DejaVuSans", fontSize=9, leading=12,
                       textColor=HexColor("#1F2937"), spaceAfter=2),
        ParagraphStyle("OA_SubHead", parent=base["Normal"],
                       fontName="DejaVuSans-Bold", fontSize=9, leading=12,
                       textColor=HexColor("#111827"), spaceBefore=4, spaceAfter=1),
        ParagraphStyle("OA_Bullet", parent=base["Normal"],
                       fontName="DejaVuSans", fontSize=9, leading=12,
                       textColor=HexColor("#1F2937"), leftIndent=12, spaceAfter=1),
        ParagraphStyle("OA_Footer", parent=base["Normal"],
                       fontName="DejaVuSans", fontSize=8, leading=10,
                       textColor=HexColor("#9CA3AF"), spaceAfter=0),
    ]
    return {s.name: s for s in defs}


def _meta_line(tender: Any) -> str:
    parts = []
    if tender.customer:
        parts.append(f"Заказчик: {_esc(tender.customer.name or '')}")
    if tender.nmck:
        parts.append(f"НМЦК: {_fmt_money(float(tender.nmck))}")
    if tender.region:
        parts.append(f"Регион: {_esc(tender.region)}")
    if tender.deadline_at:
        parts.append(f"Дедлайн: {tender.deadline_at.strftime('%d.%m.%Y')}")
    return "  ·  ".join(parts)


def _cover_page(story, styles, company_name, company_inn, company_emails, tenders):
    """Обложка: логотип + бренд + инфо компании + краткая сводка тендеров."""

    # ── Логотип + название бренда рядом ──────────────────────────────
    logo_cell = ""
    if os.path.exists(LOGO_PATH):
        logo = Image(LOGO_PATH, width=2.2 * cm, height=2.2 * cm)
        logo_cell = logo

    header_table = Table(
        [[logo_cell, Paragraph("TendeRoll", styles["OA_Brand"])]],
        colWidths=[2.8 * cm, None],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Paragraph(
        "Подобрал специально для вас тендеры",
        styles["OA_Tagline"],
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#E5E7EB"), spaceAfter=16))

    # ── Инфо о компании ───────────────────────────────────────────────
    first_email = company_emails.split("|")[0] if company_emails else ""
    info_rows = [
        [Paragraph("Компания", styles["OA_CompanyLabel"]),
         Paragraph("ИНН", styles["OA_CompanyLabel"]),
         Paragraph("Контакт", styles["OA_CompanyLabel"]),
         Paragraph("Дата", styles["OA_CompanyLabel"])],
        [Paragraph(_esc(company_name), styles["OA_CompanyValue"]),
         Paragraph(_esc(company_inn), styles["OA_CompanyValue"]),
         Paragraph(_esc(first_email), styles["OA_CompanyValue"]),
         Paragraph(date.today().strftime("%d.%m.%Y"), styles["OA_CompanyValue"])],
    ]
    info_t = Table(info_rows, colWidths=[None, 3.5 * cm, 5 * cm, 3 * cm])
    info_t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(info_t)

    # ── Краткая сводка тендеров ────────────────────────────────────────
    story.append(Paragraph("Подобранные тендеры", styles["OA_SummaryHeader"]))

    tbl_data = [[
        Paragraph("#", styles["OA_CompanyLabel"]),
        Paragraph("Тендер", styles["OA_CompanyLabel"]),
        Paragraph("НМЦК", styles["OA_CompanyLabel"]),
        Paragraph("Дедлайн", styles["OA_CompanyLabel"]),
        Paragraph("Регион", styles["OA_CompanyLabel"]),
    ]]

    for idx, item in enumerate(tenders, 1):
        t = item["tender"]
        nmck = _fmt_money(float(t.nmck)) if t.nmck else "—"
        deadline = t.deadline_at.strftime("%d.%m.%Y") if t.deadline_at else "—"
        region = _esc((t.region or "")[:30])
        title_short = _esc((t.title or "")[:110])
        customer = _esc((t.customer.name if t.customer else "")[:60])

        tbl_data.append([
            Paragraph(str(idx), styles["OA_CompanyValue"]),
            Paragraph(f"<b>{title_short}</b><br/><font color='#6B7280' size='8'>{customer}</font>",
                      styles["OA_Body"]),
            Paragraph(nmck, styles["OA_CompanyValue"]),
            Paragraph(deadline, styles["OA_CompanyValue"]),
            Paragraph(region, styles["OA_Body"]),
        ])

    summary_t = Table(tbl_data, colWidths=[0.6 * cm, None, 3 * cm, 2.5 * cm, 3.5 * cm])
    summary_t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#F9FAFB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#FFFFFF"), HexColor("#F9FAFB")]),
        ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#E5E7EB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(summary_t)

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#E5E7EB"), spaceAfter=4))
    story.append(Paragraph(
        "TendeRoll · подбор тендеров с помощью искусственного интеллекта",
        styles["OA_Footer"],
    ))


def _tender_detail_pages(story, styles, tenders):
    """По одному тендеру с полным AI-резюме — каждый со своим разрывом страницы."""
    for idx, item in enumerate(tenders, 1):
        story.append(PageBreak())
        tender = item["tender"]
        summary = item["summary"]

        story.append(Paragraph(
            f"Тендер {idx} из {len(tenders)}",
            styles["OA_TenderNum"],
        ))
        story.append(Paragraph(_esc(tender.title or ""), styles["OA_TenderTitle"]))

        meta = _meta_line(tender)
        if meta:
            story.append(Paragraph(meta, styles["OA_TenderMeta"]))

        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=HexColor("#E5E7EB"), spaceAfter=6))

        for section_title, items in _sections(summary):
            story.append(Paragraph(_esc(section_title), styles["OA_Section"]))
            for label, value in items:
                if isinstance(value, list):
                    if label:
                        story.append(Paragraph(_esc(label), styles["OA_SubHead"]))
                    for line in value:
                        story.append(Paragraph(f"• {_esc(line)}", styles["OA_Bullet"]))
                else:
                    value_esc = _esc(value)
                    if label:
                        text = (f'<font name="DejaVuSans-Bold">'
                                f'{_esc(label)}:</font> {value_esc}')
                    else:
                        text = value_esc
                    story.append(Paragraph(text, styles["OA_Body"]))

        story.append(Spacer(1, 10))
        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=HexColor("#E5E7EB"), spaceAfter=4))
        story.append(Paragraph(
            f"TendeRoll · AI-резюме тендера {idx}/{len(tenders)}",
            styles["OA_Footer"],
        ))


def render_outreach_pdf(
    company_name: str,
    company_inn: str,
    company_emails: str,
    tenders: list,  # [{"tender": Tender, "summary": dict}]
) -> BytesIO:
    buf = BytesIO()
    st = _styles()

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm,
        leftMargin=2.5 * cm, rightMargin=2.5 * cm,
    )

    story = []
    _cover_page(story, st, company_name, company_inn, company_emails, tenders)
    _tender_detail_pages(story, st, tenders)

    doc.build(story)
    buf.seek(0)
    return buf
