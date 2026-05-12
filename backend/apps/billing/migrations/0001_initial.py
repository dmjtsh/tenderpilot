import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("plan", models.CharField(choices=[("free", "Free"), ("standard", "Standard"), ("premium", "Premium")], default="free", max_length=20)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("ai_summaries_used", models.PositiveIntegerField(default=0)),
                ("rag_questions_used", models.PositiveIntegerField(default=0)),
                ("reset_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="plan",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Тариф пользователя",
                "verbose_name_plural": "Тарифы пользователей",
            },
        ),
    ]
