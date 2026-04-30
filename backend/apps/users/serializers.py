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
        fields = ["id", "email", "username", "first_name", "last_name", "date_joined"]
        read_only_fields = ["id", "date_joined"]


class CompanyProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyProfile
        fields = ["id", "name", "inn", "description", "okved_codes", "regions", "keywords", "created_at"]
        read_only_fields = ["id", "created_at"]


class CompanyDirectionSerializer(serializers.ModelSerializer):
    name = serializers.CharField(allow_blank=True, default="")

    class Meta:
        model = CompanyDirection
        fields = [
            "id", "name", "okved_codes", "keywords", "regions",
            "nmck_min", "nmck_max", "law_types",
            "vector_updated_at", "created_at",
        ]
        read_only_fields = ["id", "vector_updated_at", "created_at"]
