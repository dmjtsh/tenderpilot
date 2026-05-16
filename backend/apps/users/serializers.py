from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import User, CompanyProfile, CompanyDirection


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["email", "password", "password2", "first_name", "last_name"]

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password2"):
            raise serializers.ValidationError({"password": "Пароли не совпадают."})
        return attrs

    def create(self, validated_data):
        email = validated_data["email"]
        user = User.objects.create_user(
            username=email,
            email=email,
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
        )
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])

    def validate_old_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Неверный текущий пароль.")
        return value


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "username", "first_name", "last_name", "date_joined", "is_staff"]
        read_only_fields = ["id", "date_joined", "is_staff"]


class CompanyProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyProfile
        fields = [
            "id", "name", "inn", "description", "okved_codes", "regions", "keywords",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class CompanyDirectionSerializer(serializers.ModelSerializer):
    name = serializers.CharField(allow_blank=True, default="")

    class Meta:
        model = CompanyDirection
        fields = [
            "id", "name", "description", "okved_codes", "keywords", "regions",
            "nmck_min", "nmck_max", "law_types", "procedure_types",
            "vector_updated_at", "created_at",
        ]
        read_only_fields = ["id", "vector_updated_at", "created_at"]

    def validate(self, attrs):
        is_partial = self.partial
        instance = self.instance
        is_create = instance is None

        name = attrs.get("name", getattr(instance, "name", "") if instance else "")
        if not is_create:
            if not is_partial or "name" in attrs:
                stripped = (name or "").strip()
                if not stripped or stripped == "Новое направление":
                    raise serializers.ValidationError({
                        "name": "Укажите содержательное название направления"
                    })

        okved = attrs.get("okved_codes", getattr(instance, "okved_codes", []) if instance else [])
        keywords = attrs.get("keywords", getattr(instance, "keywords", []) if instance else [])
        if not is_create:
            if not is_partial or "okved_codes" in attrs or "keywords" in attrs:
                if not okved and not keywords:
                    raise serializers.ValidationError({
                        "non_field_errors": [
                            "Заполните хотя бы ОКВЭД или ключевые слова — "
                            "без этого рекомендации будут неточными"
                        ]
                    })

        nmck_min = attrs.get("nmck_min", getattr(instance, "nmck_min", None) if instance else None)
        nmck_max = attrs.get("nmck_max", getattr(instance, "nmck_max", None) if instance else None)
        if nmck_min is not None and nmck_max is not None and nmck_min > nmck_max:
            raise serializers.ValidationError({
                "nmck_min": "Минимальная НМЦК больше максимальной"
            })

        return attrs
