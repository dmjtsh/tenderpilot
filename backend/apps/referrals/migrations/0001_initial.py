from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("users", "0011_add_industries_to_direction"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReferralCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="referral_code",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("code", models.CharField(max_length=8, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="Referral",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "referrer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="referrals_sent",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "referred_user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="referral_origin",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "code",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="referrals",
                        to="referrals.referralcode",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("registered", "Зарегистрировался"), ("converted", "Оплатил")],
                        default="registered",
                        max_length=20,
                    ),
                ),
                ("discount_percent", models.PositiveSmallIntegerField(default=20)),
                ("discount_applied", models.BooleanField(default=False)),
                ("registered_at", models.DateTimeField(auto_now_add=True)),
                ("converted_at", models.DateTimeField(blank=True, null=True)),
            ],
        ),
    ]
