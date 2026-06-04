"""
Сигналы для обновления search_vector при сохранении тендера.
"""
from django.contrib.postgres.search import SearchVector
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="tenders.Tender")
def update_tender_search_vector(sender, instance, created: bool, **kwargs) -> None:
    """
    Обновляем search_vector после сохранения тендера.

    Пропускаем если:
    - явно передан update_fields и 'title' там отсутствует
      (например, save(update_fields=["enriched_at"]) не должен триггерить пересчёт)
    """
    update_fields = kwargs.get("update_fields")
    if update_fields is not None and "title" not in update_fields:
        return

    # Queryset update чтобы не вызвать рекурсию через post_save
    sender.objects.filter(pk=instance.pk).update(
        search_vector=SearchVector("title", config="russian"),
    )
