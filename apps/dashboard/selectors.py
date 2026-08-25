"""Dashboard aggregation selectors.

All counts are computed by database queries — never hardcoded.
"""

from django.db.models import Count, Q
from django.utils import timezone

from apps.ppe.models import PPE, PPEAssignment
from apps.projects.models import Project
from apps.tools.models import Tool
from apps.transportation.models import Vehicle
from apps.workers.models import WorkerProfile


def dashboard_summary():
    today = timezone.localdate()

    workers = WorkerProfile.objects.aggregate(
        total=Count("id"),
        active=Count(
            "id",
            filter=Q(employment_status=WorkerProfile.EmploymentStatus.ACTIVE)
            & Q(user__is_active=True),
        ),
    )

    projects = Project.objects.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(status=Project.Status.ACTIVE)),
    )

    tools = Tool.objects.aggregate(
        available=Count("id", filter=Q(availability_status=Tool.AvailabilityStatus.AVAILABLE)),
        assigned=Count("id", filter=Q(availability_status=Tool.AvailabilityStatus.ASSIGNED)),
        attention=Count(
            "id",
            filter=Q(
                availability_status__in=[
                    Tool.AvailabilityStatus.DAMAGED,
                    Tool.AvailabilityStatus.UNDER_MAINTENANCE,
                    Tool.AvailabilityStatus.LOST,
                ]
            ),
        ),
    )

    ppe_issued = PPEAssignment.objects.filter(status=PPEAssignment.Status.ACTIVE).count()
    ppe_attention = PPE.objects.filter(
        Q(expiry_date__lt=today)
        | Q(
            availability_status__in=[
                PPE.AvailabilityStatus.DAMAGED,
                PPE.AvailabilityStatus.EXPIRED,
            ]
        )
    ).count()

    vehicles = Vehicle.objects.aggregate(
        available=Count("id", filter=Q(status=Vehicle.Status.AVAILABLE)),
        in_use=Count("id", filter=Q(status=Vehicle.Status.IN_USE)),
    )

    return {
        "workers": {"total": workers["total"], "active": workers["active"]},
        "projects": {"total": projects["total"], "active": projects["active"]},
        "tools": {
            "available": tools["available"],
            "assigned": tools["assigned"],
            "attention": tools["attention"],
        },
        "ppe": {"issued": ppe_issued, "attention": ppe_attention},
        "vehicles": {
            "available": vehicles["available"],
            "in_use": vehicles["in_use"],
        },
    }
