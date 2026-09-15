from django.contrib.auth import get_user_model
from core.models import Organization, Membership


class AutoLoginMiddleware:
    """Development middleware that automatically logs in a default workspace manager.
    
    This fulfills the request to bypass the login requirement while maintaining
    all workspace, multi-tenant organization, and user session dependencies.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            User = get_user_model()
            user = User.objects.filter(is_active=True).first()
            if not user:
                user = User.objects.create_user(
                    username="demo_manager",
                    email="manager@commsos.io",
                    password="demo-password",
                    first_name="Demo",
                    last_name="Manager",
                )

            # Ensure the user has an active membership and organization
            if not Membership.objects.filter(user=user, active=True).exists():
                org = Organization.objects.first()
                if not org:
                    org = Organization.objects.create(name="CommsOS Demo")
                Membership.objects.create(
                    user=user,
                    organization=org,
                    role=Membership.Role.COMMUNICATIONS_MANAGER,
                )

            request.user = user

        return self.get_response(request)
