from django.db import migrations

CHAT_QA_V1_TEMPLATE = """Ты эксперт по госзакупкам России.
Отвечай ТОЛЬКО на основе документации тендера ниже.
Если ответа нет в документах — скажи об этом прямо.
Не придумывай и не используй общие знания.

ДОКУМЕНТАЦИЯ:
{context}

ВОПРОС: {question}"""


def seed_chat_qa_v1(apps, schema_editor):
    PromptTemplate = apps.get_model("tenders", "PromptTemplate")
    PromptTemplate.objects.get_or_create(
        name="chat_qa_v1",
        version=1,
        defaults={
            "user_template": CHAT_QA_V1_TEMPLATE,
            "description": "RAG QA prompt for tender chat — answers questions based on document chunks",
            "is_active": True,
        },
    )


def remove_chat_qa_v1(apps, schema_editor):
    PromptTemplate = apps.get_model("tenders", "PromptTemplate")
    PromptTemplate.objects.filter(name="chat_qa_v1", version=1).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tenders", "0015_add_actual_model"),
    ]

    operations = [
        migrations.RunPython(seed_chat_qa_v1, remove_chat_qa_v1),
    ]
