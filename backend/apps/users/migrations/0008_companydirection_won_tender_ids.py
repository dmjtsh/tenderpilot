from django.db import migrations, models
import django.contrib.postgres.fields


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0007_companydirection_exclude_keywords"),
    ]

    operations = [
        migrations.AddField(
            model_name="companydirection",
            name="won_tender_ids",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.IntegerField(),
                blank=True,
                default=list,
                size=None,
            ),
        ),
    ]
