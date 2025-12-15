"""
Accounts API (Employees)

CRUD operations for employee/user management.
"""
from django.db import models
from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view

from .models import LocalUser
from apps.core.api_base import IsAuthenticated, IsAdmin, SuccessResponseSerializer, ErrorResponseSerializer


# =============================================================================
# Serializers
# =============================================================================

class EmployeeListSerializer(serializers.ModelSerializer):
    """Serializer for listing employees"""
    initials = serializers.CharField(source='get_initials', read_only=True)
    role_color = serializers.CharField(source='get_role_color', read_only=True)

    class Meta:
        model = LocalUser
        fields = [
            'id', 'name', 'email', 'role', 'is_active',
            'language', 'avatar', 'initials', 'role_color',
            'created_at', 'last_login'
        ]
        read_only_fields = ['id', 'created_at', 'last_login', 'initials', 'role_color']


class EmployeeDetailSerializer(serializers.ModelSerializer):
    """Serializer for employee detail view"""
    initials = serializers.CharField(source='get_initials', read_only=True)
    role_color = serializers.CharField(source='get_role_color', read_only=True)
    has_pin = serializers.SerializerMethodField()

    class Meta:
        model = LocalUser
        fields = [
            'id', 'cloud_user_id', 'name', 'email', 'role',
            'is_active', 'language', 'avatar', 'initials',
            'role_color', 'has_pin', 'created_at', 'updated_at', 'last_login'
        ]
        read_only_fields = [
            'id', 'cloud_user_id', 'created_at', 'updated_at',
            'last_login', 'initials', 'role_color', 'has_pin'
        ]

    def get_has_pin(self, obj):
        return bool(obj.pin_hash)


class EmployeeCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating employees"""
    pin = serializers.CharField(
        write_only=True,
        max_length=4,
        min_length=4,
        help_text="4-digit PIN code"
    )

    class Meta:
        model = LocalUser
        fields = ['name', 'email', 'role', 'language', 'pin']

    def validate_pin(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("PIN must contain only digits")
        return value

    def validate_email(self, value):
        if LocalUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already exists")
        return value

    def create(self, validated_data):
        pin = validated_data.pop('pin')
        validated_data['cloud_user_id'] = 0  # Temporary, synced later
        user = LocalUser.objects.create(**validated_data)
        user.set_pin(pin)
        return user


class EmployeeUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating employees"""

    class Meta:
        model = LocalUser
        fields = ['name', 'email', 'role', 'language', 'is_active']

    def validate_email(self, value):
        instance = self.instance
        if instance and instance.email != value:
            if LocalUser.objects.filter(email=value).exists():
                raise serializers.ValidationError("Email already exists")
        return value


class ResetPinSerializer(serializers.Serializer):
    """Serializer for resetting employee PIN"""
    pin = serializers.CharField(
        max_length=4,
        min_length=4,
        help_text="New 4-digit PIN code"
    )

    def validate_pin(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("PIN must contain only digits")
        return value


# =============================================================================
# ViewSet
# =============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List employees",
        description="Get list of all employees. Filter by is_active, role, or search.",
        tags=['Employees']
    ),
    retrieve=extend_schema(
        summary="Get employee",
        description="Get details of a specific employee",
        tags=['Employees']
    ),
    create=extend_schema(
        summary="Create employee",
        description="Create a new employee with PIN",
        tags=['Employees']
    ),
    update=extend_schema(
        summary="Update employee",
        description="Update employee information",
        tags=['Employees']
    ),
    partial_update=extend_schema(
        summary="Partial update employee",
        description="Partially update employee information",
        tags=['Employees']
    ),
    destroy=extend_schema(
        summary="Delete employee",
        description="Soft delete an employee (mark as inactive)",
        tags=['Employees']
    ),
)
class EmployeeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing employees.

    Provides CRUD operations plus custom actions for PIN reset.

    **Filters:**
    - `is_active`: Filter by active status (true/false)
    - `role`: Filter by role (admin/cashier/seller)
    - `search`: Search by name or email
    """
    queryset = LocalUser.objects.all().order_by('name')
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'list':
            return EmployeeListSerializer
        elif self.action == 'create':
            return EmployeeCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return EmployeeUpdateSerializer
        elif self.action == 'reset_pin':
            return ResetPinSerializer
        return EmployeeDetailSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        # Filter by role
        role = self.request.query_params.get('role')
        if role:
            queryset = queryset.filter(role=role)

        # Search by name or email
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search) |
                models.Q(email__icontains=search)
            )

        return queryset

    def destroy(self, request, *args, **kwargs):
        """Soft delete - mark as inactive instead of deleting."""
        instance = self.get_object()

        # Prevent deleting admin users
        if instance.role == 'admin':
            return Response(
                {'success': False, 'error': 'Cannot delete admin users'},
                status=status.HTTP_400_BAD_REQUEST
            )

        instance.is_active = False
        instance.save()
        return Response({'success': True, 'message': 'Employee deactivated'})

    @extend_schema(
        summary="Reset employee PIN",
        description="Reset the PIN code for an employee",
        request=ResetPinSerializer,
        responses={
            200: SuccessResponseSerializer,
            400: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
        },
        tags=['Employees']
    )
    @action(detail=True, methods=['post'], url_path='reset-pin')
    def reset_pin(self, request, pk=None):
        """Reset the PIN for an employee."""
        employee = self.get_object()
        serializer = ResetPinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        employee.set_pin(serializer.validated_data['pin'])
        return Response({'success': True, 'message': 'PIN reset successfully'})

    @extend_schema(
        summary="Activate employee",
        description="Reactivate a deactivated employee",
        responses={200: SuccessResponseSerializer, 404: ErrorResponseSerializer},
        tags=['Employees']
    )
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Reactivate a deactivated employee."""
        employee = self.get_object()
        employee.is_active = True
        employee.save()
        return Response({'success': True, 'message': 'Employee activated'})

    @extend_schema(
        summary="Deactivate employee",
        description="Deactivate an active employee",
        responses={200: SuccessResponseSerializer, 400: ErrorResponseSerializer, 404: ErrorResponseSerializer},
        tags=['Employees']
    )
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate an employee."""
        employee = self.get_object()

        if employee.role == 'admin':
            return Response(
                {'success': False, 'error': 'Cannot deactivate admin users'},
                status=status.HTTP_400_BAD_REQUEST
            )

        employee.is_active = False
        employee.save()
        return Response({'success': True, 'message': 'Employee deactivated'})


# =============================================================================
# URL Patterns
# =============================================================================

from django.urls import path, include
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register('', EmployeeViewSet, basename='employees')

api_urlpatterns = router.urls
