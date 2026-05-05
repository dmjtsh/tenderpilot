from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenders", "0009_backfill_procedure_type"),
        ("users", "0004_multi_profile"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenderpipeline",
            name="profile",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="pipeline_entries",
                to="users.companyprofile",
            ),
        ),
    ]
