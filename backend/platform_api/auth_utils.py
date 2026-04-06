from django.conf import settings
from django.contrib.auth.models import User


def ensure_admin_user() -> User:
    email = settings.DJANGO_ADMIN_EMAIL
    password = settings.DJANGO_ADMIN_PASSWORD

    user, _ = User.objects.get_or_create(
        username=email,
        defaults={
            "email": email,
            "is_staff": True,
            "is_superuser": True,
        },
    )

    updates = []
    if user.email != email:
        user.email = email
        updates.append("email")
    if not user.is_staff:
        user.is_staff = True
        updates.append("is_staff")
    if not user.is_superuser:
        user.is_superuser = True
        updates.append("is_superuser")
    if not user.check_password(password):
        user.set_password(password)
        updates.append("password")

    if updates:
        user.save()

    return user
