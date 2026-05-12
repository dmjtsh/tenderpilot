from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import get_billing_info


class BillingInfoView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        data = get_billing_info(request.user)
        return Response({"data": data, "error": None})
