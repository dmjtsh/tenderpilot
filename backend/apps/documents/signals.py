from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.documents.models import TenderDocument


@receiver(post_save, sender=TenderDocument)
def invalidate_summary_on_new_doc(sender, instance: TenderDocument, **kwargs) -> None:
    if instance.parse_status == TenderDocument.ParseStatus.DONE:
        from apps.tenders.models import Tender
        Tender.objects.filter(id=instance.tender_id).update(ai_summary="")
