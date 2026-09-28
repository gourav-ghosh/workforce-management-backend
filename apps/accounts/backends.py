"""Custom authentication backend supporting mobile-number login."""

from django.contrib.auth import get_user_model, hashers
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


class MobileNumberAuthBackend(ModelBackend):
    """Authenticate users by ``mobile_number`` instead of ``username``.

    SimpleJWT's ``TokenObtainPairSerializer`` calls ``authenticate()`` with
    ``{self.username_field: value}``; setting ``username_field =
    "mobile_number"`` on the serializer makes this backend receive the
    mobile number as the lookup key.
    """

    def authenticate(self, request, mobile_number=None, password=None):
        if mobile_number is None or password is None:
            return None
        try:
            user = User._default_manager.get(mobile_number=mobile_number)
        except User.DoesNotExist:
            # Run the default password hasher once to reduce timing attacks.
            hashers.make_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None