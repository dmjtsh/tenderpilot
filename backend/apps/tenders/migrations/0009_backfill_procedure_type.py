import re
from django.db import migrations


_PROCEDURE_URL_MAP = [
    (r"/notice/ea(?:20|44)/", "auction"),
    (r"/notice/ok(?:20|44)/", "contest"),
    (r"/notice/zk(?:20|44)/", "request_quotations"),
    (r"/notice/(?:ezt20|zp44)/", "request_proposals"),
]


def _detect(url: str) -> str:
    for pattern, proc_type in _PROCEDURE_URL_MAP:
        if re.search(pattern, url):
            return proc_type
    return "other"


def backfill(apps, schema_editor):
    Tender = apps.get_model("tenders", "Tender")
    updates = []
    for pk, url in Tender.objects.values_list("pk", "source_url"):
        pt = _detect(url)
        if pt != "other":
            updates.append((pk, pt))
    for pk, pt in updates:
        Tender.objects.filter(pk=pk).update(procedure_type=pt)


class Migration(migrations.Migration):
    dependencies = [
        ("tenders", "0008_procedure_type"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
