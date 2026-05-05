from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenders", "0010_pipeline_profile"),
    ]

    operations = [
        # 1. Добавляем source с дефолтом 'eis' — все существующие тендеры становятся eis
        migrations.AddField(
            model_name="tender",
            name="source",
            field=models.CharField(
                choices=[
                    ("eis", "ЕИС (zakupki.gov.ru)"),
                    ("bidzaar", "Bidzaar"),
                    ("other", "Другой источник"),
                ],
                default="eis",
                db_index=True,
                max_length=20,
            ),
        ),
        # 2. Убираем старый unique constraint на number
        migrations.AlterField(
            model_name="tender",
            name="number",
            field=models.CharField(max_length=50, db_index=True),
        ),
        # 3. Добавляем composite unique (number, source)
        migrations.AddConstraint(
            model_name="tender",
            constraint=models.UniqueConstraint(
                fields=["number", "source"],
                name="unique_number_per_source",
            ),
        ),
        # 4. Добавляем b2b в LawType (только метаданные Django, не меняет схему БД)
        migrations.AlterField(
            model_name="tender",
            name="law_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("44-ФЗ", "44-ФЗ"),
                    ("223-ФЗ", "223-ФЗ"),
                    ("615-ПП", "615-ПП"),
                    ("b2b", "Коммерческая закупка"),
                ],
                db_index=True,
                max_length=10,
            ),
        ),
    ]
