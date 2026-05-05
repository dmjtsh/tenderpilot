# Generated manually — remove active_profile concept

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_multi_profile'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='user',
            name='active_profile',
        ),
    ]
