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


def _get_active_profile(user: User) -> CompanyProfile:
    """Возвращает активный профиль (или последний созданный, или создаёт новый)."""
    if user.active_profile_id:
        try:
            return CompanyProfile.objects.get(pk=user.active_profile_id, user=user)
        except CompanyProfile.DoesNotExist:
            pass
    # fallback: последний созданный
    profile = CompanyProfile.objects.filter(user=user).order_by("-created_at").first()
    if profile:
        User.objects.filter(pk=user.pk).update(active_profile=profile)
        user.active_profile_id = profile.pk
        return profile
    # создаём пустой профиль
    profile = CompanyProfile.objects.create(user=user, name="")
    User.objects.filter(pk=user.pk).update(active_profile=profile)
    user.active_profile_id = profile.pk
    return profile


# ─── Backward-compat single-company endpoints ────────────────────────────────

class CompanyProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = CompanyProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx

    def get_object(self):
        return _get_active_profile(self.request.user)


# ─── Multi-company CRUD ───────────────────────────────────────────────────────

class CompanyProfileListCreateView(generics.ListCreateAPIView):
    serializer_class = CompanyProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx

    def get_queryset(self):
        return CompanyProfile.objects.filter(user=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        profile = serializer.save(user=self.request.user)
        # новый профиль становится активным
        User.objects.filter(pk=self.request.user.pk).update(active_profile=profile)
        self.request.user.active_profile_id = profile.pk


class CompanyProfileDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CompanyProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx

    def get_queryset(self):
        return CompanyProfile.objects.filter(user=self.request.user)

    def perform_destroy(self, instance):
        user = self.request.user
        was_active = user.active_profile_id == instance.pk
        instance.delete()
        if was_active:
            remaining = CompanyProfile.objects.filter(user=user).order_by("-created_at").first()
            User.objects.filter(pk=user.pk).update(active_profile=remaining)


class CompanyProfileActivateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        try:
            profile = CompanyProfile.objects.get(pk=pk, user=request.user)
        except CompanyProfile.DoesNotExist:
            return Response({"data": None, "error": "Профиль не найден"}, status=status.HTTP_404_NOT_FOUND)
        User.objects.filter(pk=request.user.pk).update(active_profile=profile)
        request.user.active_profile_id = profile.pk
        return Response({
            "data": CompanyProfileSerializer(profile, context={"request": request}).data,
            "error": None,
        })


# ─── Directions ───────────────────────────────────────────────────────────────

def _resolve_profile(request, profile_id: int | None = None) -> CompanyProfile | None:
    if profile_id:
        try:
            return CompanyProfile.objects.get(pk=profile_id, user=request.user)
        except CompanyProfile.DoesNotExist:
            return None
    return _get_active_profile(request.user)


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
