from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import BasePermission

from .errors import DomainError
from .models import Workspace


class WorkspacePermission(BasePermission):
    def has_permission(self, request, view):
        workspace_id = request.session.get("workspace_id")
        workspace = (
            Workspace.objects.filter(pk=workspace_id, expires_at__gt=timezone.now()).first()
            if workspace_id
            else None
        )
        if not workspace:
            raise DomainError("session_expired", "Создайте новую гостевую сессию", 401)
        request.workspace = workspace
        if request.method not in ["GET", "HEAD", "OPTIONS"]:
            # DRF SessionAuthentication сам не защищает анонимные Django-сессии.
            SessionAuthentication().enforce_csrf(request)
        return True
