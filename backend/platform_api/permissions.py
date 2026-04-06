from django.conf import settings
from rest_framework.permissions import BasePermission


class IsTradeflowAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.email == settings.DJANGO_ADMIN_EMAIL
        )
