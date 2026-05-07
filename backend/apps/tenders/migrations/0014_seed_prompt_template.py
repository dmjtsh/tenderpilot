from django.db import migrations

SUMMARY_V1_TEMPLATE = """Ты эксперт по госзакупкам России.
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
    "risk_assessment": "оценка рисков заказчика или пустая строка",
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


def seed_prompt(apps, schema_editor):
    PromptTemplate = apps.get_model("tenders", "PromptTemplate")
    PromptTemplate.objects.get_or_create(
        name="summary_v1",
        version=1,
        defaults={
            "user_template": SUMMARY_V1_TEMPLATE,
            "description": "Базовый промпт AI-резюме тендера v2 (4-секционный JSON)",
        },
    )


def unseed_prompt(apps, schema_editor):
    PromptTemplate = apps.get_model("tenders", "PromptTemplate")
    PromptTemplate.objects.filter(name="summary_v1", version=1).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tenders", "0013_add_experiment_platform"),
    ]

    operations = [
        migrations.RunPython(seed_prompt, unseed_prompt),
    ]
