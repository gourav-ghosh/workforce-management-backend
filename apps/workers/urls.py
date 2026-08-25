from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.workers.views import WorkerViewSet

router = DefaultRouter()
router.register("", WorkerViewSet, basename="workers")

urlpatterns = [
    path("", include(router.urls)),
]
