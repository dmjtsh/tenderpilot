import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="users.CompanyDirection")
def schedule_vector_rebuild(sender, instance, **kwargs):
    if not instance.needs_reindex():
        return

    from apps.search.tasks import rebuild_direction_vector

    rebuild_direction_vector.apply_async(
        args=[instance.id],
        countdown=30,
        task_id=f"direction-vector-{instance.id}",
    )
    logger.info("Scheduled vector rebuild for direction %d", instance.id)
