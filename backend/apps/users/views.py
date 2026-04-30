from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from .models import CompanyProfile, CompanyDirection
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


class CompanyProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = CompanyProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        profile, _ = CompanyProfile.objects.get_or_create(user=self.request.user)
        return profile


class CompanyDirectionListCreateView(generics.ListCreateAPIView):
    serializer_class = CompanyDirectionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        profile, _ = CompanyProfile.objects.get_or_create(user=self.request.user)
        return CompanyDirection.objects.filter(profile=profile).order_by("created_at")

    def perform_create(self, serializer):
        profile, _ = CompanyProfile.objects.get_or_create(user=self.request.user)
        serializer.save(profile=profile)


class CompanyDirectionDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CompanyDirectionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        profile, _ = CompanyProfile.objects.get_or_create(user=self.request.user)
        return CompanyDirection.objects.filter(profile=profile)


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
