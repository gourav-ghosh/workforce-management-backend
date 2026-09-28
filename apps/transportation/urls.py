from django.urls import path

from apps.transportation.views import (
    VehicleAssignView,
    VehicleBookingCalendarView,
    VehicleBookingDetailView,
    VehicleBookingListCreateView,
    VehicleDetailView,
    VehicleHistoryView,
    VehicleListCreateView,
    VehicleMediaView,
    VehicleSetStatusView,
    VehicleStockSummaryView,
    VehicleUnassignView,
)

urlpatterns = [
    path("", VehicleListCreateView.as_view(), name="vehicle-list"),
    path("stock/", VehicleStockSummaryView.as_view(), name="vehicle-stock"),
    path(
        "bookings/",
        VehicleBookingCalendarView.as_view(),
        name="vehicle-booking-calendar",
    ),
    path("<str:vehicle_id>/", VehicleDetailView.as_view(), name="vehicle-detail"),
    path("<str:vehicle_id>/assign/", VehicleAssignView.as_view(), name="vehicle-assign"),
    path("<str:vehicle_id>/unassign/", VehicleUnassignView.as_view(), name="vehicle-unassign"),
    path("<str:vehicle_id>/history/", VehicleHistoryView.as_view(), name="vehicle-history"),
    path("<str:vehicle_id>/media/", VehicleMediaView.as_view(), name="vehicle-media"),
    path("<str:vehicle_id>/set-status/", VehicleSetStatusView.as_view(), name="vehicle-set-status"),
    path(
        "<str:vehicle_id>/bookings/",
        VehicleBookingListCreateView.as_view(),
        name="vehicle-booking-list",
    ),
    path(
        "<str:vehicle_id>/bookings/<int:booking_id>/",
        VehicleBookingDetailView.as_view(),
        name="vehicle-booking-detail",
    ),
]
