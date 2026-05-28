from datetime import date
from io import BytesIO
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
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


def _get_outreach_styles():
    _register_fonts()
    base = getSampleStyleSheet()

    extra = [
        ParagraphStyle(
            "OA_MainTitle",
            parent=base["Normal"],
            fontName="DejaVuSans-Bold",
            fontSize=18,
            leading=22,
            textColor=HexColor("#111827"),
            spaceAfter=6,
        ),
        ParagraphStyle(
            "OA_CompanyInfo",
            parent=base["Normal"],
            fontName="DejaVuSans",
            fontSize=10,
            leading=14,
            textColor=HexColor("#374151"),
            spaceAfter=2,
        ),
        ParagraphStyle(
            "OA_TenderTitle",
            parent=base["Normal"],
            fontName="DejaVuSans-Bold",
            fontSize=13,
            leading=17,
            textColor=HexColor("#111827"),
            spaceBefore=10,
            spaceAfter=4,
        ),
        ParagraphStyle(
            "OA_TenderMeta",
            parent=base["Normal"],
            fontName="DejaVuSans",
            fontSize=9,
            leading=12,
            textColor=HexColor("#6B7280"),
            spaceAfter=6,
        ),
        ParagraphStyle(
            "OA_Section",
            parent=base["Normal"],
            fontName="DejaVuSans-Bold",
            fontSize=11,
            leading=14,
            textColor=HexColor("#1D4ED8"),
            spaceBefore=10,
            spaceAfter=4,
        ),
        ParagraphStyle(
            "OA_Body",
            parent=base["Normal"],
            fontName="DejaVuSans",
            fontSize=9,
            leading=12,
            textColor=HexColor("#1F2937"),
            spaceAfter=2,
        ),
        ParagraphStyle(
            "OA_SubHead",
            parent=base["Normal"],
            fontName="DejaVuSans-Bold",
            fontSize=9,
            leading=12,
            textColor=HexColor("#111827"),
            spaceBefore=4,
            spaceAfter=1,
        ),
        ParagraphStyle(
            "OA_Bullet",
            parent=base["Normal"],
            fontName="DejaVuSans",
            fontSize=9,
            leading=12,
            textColor=HexColor("#1F2937"),
            leftIndent=12,
            spaceAfter=1,
        ),
        ParagraphStyle(
            "OA_Footer",
            parent=base["Normal"],
            fontName="DejaVuSans",
            fontSize=8,
            leading=10,
            textColor=HexColor("#9CA3AF"),
            spaceAfter=0,
        ),
    ]

    styles = {}
    for s in extra:
        styles[s.name] = s
    return styles


def _tender_meta_line(tender: Any) -> str:
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


def render_outreach_pdf(
    company_name: str,
    company_inn: str,
    company_emails: str,
    tenders: list[dict],  # [{"tender": Tender, "summary": dict}]
) -> BytesIO:
    buf = BytesIO()
    styles = _get_outreach_styles()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
    )

    story: list = []

    # ── Обложка ──────────────────────────────────────────────────────────
    story.append(
        Paragraph("Подобрали тендеры специально для вас", styles["OA_MainTitle"])
    )
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#E5E7EB"), spaceAfter=8))

    company_block = [
        [
            Paragraph('<font name="DejaVuSans-Bold">Компания:</font>', styles["OA_CompanyInfo"]),
            Paragraph(_esc(company_name), styles["OA_CompanyInfo"]),
        ],
        [
            Paragraph('<font name="DejaVuSans-Bold">ИНН:</font>', styles["OA_CompanyInfo"]),
            Paragraph(_esc(company_inn), styles["OA_CompanyInfo"]),
        ],
    ]
    if company_emails:
        first_email = company_emails.split("|")[0]
        company_block.append([
            Paragraph('<font name="DejaVuSans-Bold">Контакт:</font>', styles["OA_CompanyInfo"]),
            Paragraph(_esc(first_email), styles["OA_CompanyInfo"]),
        ])
    company_block.append([
        Paragraph('<font name="DejaVuSans-Bold">Дата:</font>', styles["OA_CompanyInfo"]),
        Paragraph(date.today().strftime("%d.%m.%Y"), styles["OA_CompanyInfo"]),
    ])

    t = Table(company_block, colWidths=[3.5 * cm, None])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(t)
    story.append(Spacer(1, 12))

    # ── Тендеры ───────────────────────────────────────────────────────────
    for idx, item in enumerate(tenders, 1):
        tender = item["tender"]
        summary = item["summary"]

        story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#6366F1"), spaceAfter=6))
        story.append(
            Paragraph(f"Тендер {idx} из {len(tenders)}: {_esc(tender.title or '')}", styles["OA_TenderTitle"])
        )

        meta = _tender_meta_line(tender)
        if meta:
            story.append(Paragraph(meta, styles["OA_TenderMeta"]))

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
                        text = f'<font name="DejaVuSans-Bold">{_esc(label)}:</font> {value_esc}'
                    else:
                        text = value_esc
                    story.append(Paragraph(text, styles["OA_Body"]))

        story.append(Spacer(1, 8))

    # ── Footer ────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#E5E7EB"), spaceAfter=4))
    story.append(
        Paragraph(
            "Сформировано TenderPilot · tenderpilot.ru · Персональная подборка",
            styles["OA_Footer"],
        )
    )

    doc.build(story)
    buf.seek(0)
    return buf
