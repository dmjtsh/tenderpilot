# Generated manually — multi-company profile support

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_procedure_type'),
    ]

    operations = [
        # 1. Change CompanyProfile.user from OneToOneField to ForeignKey
        migrations.AlterField(
            model_name='companyprofile',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='company_profiles',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # 2. Add User.active_profile nullable FK
        migrations.AddField(
            model_name='user',
            name='active_profile',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='active_for_users',
                to='users.companyprofile',
            ),
        ),
    ]
