from django.core.management.base import BaseCommand

from apps.users.models import User
from apps.referrals.models import ReferralCode


class Command(BaseCommand):
    help = "Generate referral codes for all existing users who don't have one"

    def handle(self, *args, **options):
        existing_ids = set(ReferralCode.objects.values_list("user_id", flat=True))
        users = User.objects.exclude(pk__in=existing_ids)
        count = 0
        for user in users:
            ReferralCode.objects.create(user=user)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Created {count} referral codes"))
