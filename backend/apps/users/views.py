from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User, CompanyProfile, CompanyDirection
from .serializers import (
    UserSerializer,
    CompanyProfileSerializer,
    CompanyDirectionSerializer,
    RegisterSerializer,
    ChangePasswordSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "data": {
                    "user": UserSerializer(user).data,
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                },
                "error": None,
            },
            status=status.HTTP_201_CREATED,
        )


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save()
        return Response({"data": {"detail": "Пароль изменён."}, "error": None})


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from .services import send_password_reset_email
        send_password_reset_email(serializer.validated_data["email"])
        return Response({"data": {"detail": "Если аккаунт существует, письмо отправлено."}, "error": None})


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from .services import confirm_password_reset
        from django.core.exceptions import ValidationError
        try:
            confirm_password_reset(
                uid=serializer.validated_data["uid"],
                token=serializer.validated_data["token"],
                new_password=serializer.validated_data["new_password"],
            )
        except ValidationError as e:
            messages = e.messages if hasattr(e, "messages") else [str(e.message)]
            return Response(
                {"data": None, "error": "; ".join(messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"data": {"detail": "Пароль успешно изменён."}, "error": None})


def _get_first_profile(user: User) -> CompanyProfile:
    """Возвращает первый (последний созданный) профиль или создаёт пустой."""
    profile = CompanyProfile.objects.filter(user=user).order_by("-created_at").first()
    if profile:
        return profile
    return CompanyProfile.objects.create(user=user, name="")


def _trigger_won_tender_embeds(old_ids: list, new_ids: list) -> None:
    """Запускает embed_tender(force=True) для новых won-тендеров."""
    added = set(new_ids or []) - set(old_ids or [])
    if not added:
        return
    from apps.tenders.models import Tender
    from apps.search.tasks import embed_tender
    for tid in added:
        try:
            Tender.objects.only("id").get(pk=tid)
            # Всегда запускаем embed — upsert идемпотентен,
            # а embedding_id в Postgres может расходиться с реальным Qdrant
            embed_tender.apply_async(args=[tid], kwargs={"force": True})
        except Tender.DoesNotExist:
            pass


def _cleanup_won_tender_vectors(old_ids: list, new_ids: list) -> None:
    """Удаляет из Qdrant векторы won-тендеров которые убрали из профиля, если они не active."""
    removed = set(old_ids or []) - set(new_ids or [])
    if not removed:
        return
    from apps.tenders.models import Tender
    from apps.search.services import qdrant
    for tid in removed:
        try:
            tender = Tender.objects.only("id", "status", "embedding_id").get(pk=tid)
            if tender.status != Tender.Status.ACTIVE and tender.embedding_id:
                qdrant.delete_tender(tid)
                Tender.objects.filter(pk=tid).update(embedding_id=None)
        except Tender.DoesNotExist:
            pass


# ─── Backward-compat single-company endpoints ────────────────────────────────

class CompanyProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = CompanyProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return _get_first_profile(self.request.user)

    def perform_update(self, serializer):
        old_ids = list(serializer.instance.won_tender_ids or [])
        instance = serializer.save()
        new_ids = instance.won_tender_ids or []
        _trigger_won_tender_embeds(old_ids, new_ids)
        _cleanup_won_tender_vectors(old_ids, new_ids)


# ─── Multi-company CRUD ───────────────────────────────────────────────────────

class CompanyProfileListCreateView(generics.ListCreateAPIView):
    serializer_class = CompanyProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return CompanyProfile.objects.filter(user=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        from apps.billing.services import check_company_limit
        from apps.billing.exceptions import QuotaExceeded
        from rest_framework.exceptions import PermissionDenied

        try:
            check_company_limit(self.request.user)
        except QuotaExceeded as e:
            raise PermissionDenied(detail=e.detail)
        serializer.save(user=self.request.user)


class CompanyProfileDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CompanyProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return CompanyProfile.objects.filter(user=self.request.user)

    def perform_update(self, serializer):
        old_ids = list(serializer.instance.won_tender_ids or [])
        instance = serializer.save()
        new_ids = instance.won_tender_ids or []
        _trigger_won_tender_embeds(old_ids, new_ids)
        _cleanup_won_tender_vectors(old_ids, new_ids)


# ─── Directions ───────────────────────────────────────────────────────────────

def _resolve_profile(request, profile_id: int | None = None) -> CompanyProfile | None:
    if profile_id:
        try:
            return CompanyProfile.objects.get(pk=profile_id, user=request.user)
        except CompanyProfile.DoesNotExist:
            return None
    return _get_first_profile(request.user)


class CompanyDirectionListCreateView(generics.ListCreateAPIView):
    serializer_class = CompanyDirectionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _profile(self):
        pid = self.kwargs.get("profile_pk") or self.request.query_params.get("profile_id")
        return _resolve_profile(self.request, int(pid) if pid else None)

    def get_queryset(self):
        profile = self._profile()
        if not profile:
            return CompanyDirection.objects.none()
        return CompanyDirection.objects.filter(profile=profile).order_by("created_at")

    def perform_create(self, serializer):
        profile = self._profile()
        serializer.save(profile=profile)


class CompanyDirectionDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CompanyDirectionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return CompanyDirection.objects.filter(profile__user=self.request.user)


class InnLookupView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        inn = (request.data.get("inn") or "").strip()
        if not inn or len(inn) not in (10, 12) or not inn.isdigit():
            return Response({"data": None, "error": "Введите корректный ИНН (10 или 12 цифр)"})

        from .dadata import enrich_company_by_inn
        from apps.tenders.okved import OKVED_NAMES, okved_to_text

        info = enrich_company_by_inn(inn)
        if not info:
            return Response({"data": None, "error": "Компания не найдена в реестре"})

        # Формируем предложенные направления: один ОКВЭД → одно направление
        suggested_directions = []
        for code in info["okved_list"]:
            name = (
                OKVED_NAMES.get(code)
                or OKVED_NAMES.get(code[:4])
                or OKVED_NAMES.get(code[:2])
                or code
            )
            suggested_directions.append({
                "okved_code": code,
                "name": name.capitalize(),
            })

        return Response({
            "data": {
                "name": info["name"],
                "full_name": info["full_name"],
                "inn": info["inn"],
                "region": info["region"],
                "okved_main": info["okved_main"],
                "okved_list": info["okved_list"],
                "suggested_directions": suggested_directions,
            },
            "error": None,
        })
