from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tenders', '0026_add_docs_download_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='tender',
            name='search_vector',
            field=SearchVectorField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name='tender',
            index=GinIndex(fields=['search_vector'], name='tender_search_vector_gin'),
        ),
    ]
