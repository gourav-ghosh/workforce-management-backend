from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.transportation.views import VehicleViewSet

router = DefaultRouter()
router.register("", VehicleViewSet, basename="vehicles")

urlpatterns = [
    path("", include(router.urls)),
]
