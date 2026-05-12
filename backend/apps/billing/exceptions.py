from rest_framework.exceptions import APIException


class QuotaExceeded(APIException):
    status_code = 402
    default_code = "quota_exceeded"

    def __init__(self, resource: str, used: int, limit: int, plan: str) -> None:
        self.resource = resource
        self.used = used
        self.limit = limit
        self.plan = plan
        detail = {
            "resource": resource,
            "used": used,
            "limit": limit,
            "plan": plan,
        }
        super().__init__(detail=detail)
