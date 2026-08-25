from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.ppe.views import PPEViewSet

router = DefaultRouter()
router.register("", PPEViewSet, basename="ppe")

urlpatterns = [
    path("", include(router.urls)),
]
