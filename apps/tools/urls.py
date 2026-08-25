from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.tools.views import ToolViewSet

router = DefaultRouter()
router.register("", ToolViewSet, basename="tools")

urlpatterns = [
    path("", include(router.urls)),
]
