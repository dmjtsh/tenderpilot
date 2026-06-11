from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services


class ReferralMeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        code = services.get_or_create_code(user)
        link = services.get_referral_link(user)
        stats = services.get_stats(user)
        return Response({
            "data": {
                "code": code,
                "link": link,
                **stats,
            },
            "error": None,
        })
