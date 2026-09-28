"""Seed realistic demo data for development environments.

Usage:
    python manage.py seed_demo_data

Creates an admin account, worker accounts (with login credentials),
projects, tools, PPE items, vehicles and sample assignments including
returned/history records. Idempotent: existing records are skipped.

Demo credentials (DEVELOPMENT ONLY - never use in production):
    Login uses the *mobile number*, not the legacy username.
    admin    mobile 9000000000 / Admin@12345
    workers  mobile 9876543210 ... 9876543217 / Worker@12345
"""

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import record_audit
from apps.ppe.models import PPE, PPEAssignment, PPEMedia  # noqa: F401
from apps.projects.models import Project, ProjectWorker
from apps.tools.models import Tool, ToolAssignment, ToolDamage
from apps.transportation.models import Vehicle, VehicleAssignment
from apps.workers.models import WorkerProfile

# Retained only for the legacy Django `username` column; login uses
# ADMIN_MOBILE because User.USERNAME_FIELD is `mobile_number`.
ADMIN_USERNAME = "admin"
ADMIN_MOBILE = "9000000000"
ADMIN_PASSWORD = "Admin@12345"
WORKER_PASSWORD = "Worker@12345"

WORKERS = [
    ("EMP001", "Ramesh Kumar", "9876543210", "Site Supervisor"),
    ("EMP002", "Suresh Prasad", "9876543211", "Mason"),
    ("EMP003", "Anil Sharma", "9876543212", "Electrician"),
    ("EMP004", "Vijay Singh", "9876543213", "Welder"),
    ("EMP005", "Deepak Verma", "9876543214", "Plumber"),
    ("EMP006", "Sanjay Yadav", "9876543215", "Driver"),
    ("EMP007", "Manoj Gupta", "9876543216", "Carpenter"),
    ("EMP008", "Prakash Jha", "9876543217", "Helper"),
]

PROJECTS = [
    (
        "PRJ-1001",
        "Ranchi Tower Electrical Works",
        "Sharma Constructions",
        "Ranchi, Jharkhand",
        Project.Status.ACTIVE,
        Project.MeasurementSheetStatus.SUBMITTED,
        25,
        "Electrical fitting and wiring",
    ),
    (
        "PRJ-1002",
        "Jamshedpur Plant Maintenance",
        "Tata Industries",
        "Jamshedpur, Jharkhand",
        Project.Status.ACTIVE,
        Project.MeasurementSheetStatus.NOT_SUBMITTED,
        18,
        "Annual plant maintenance",
    ),
    (
        "PRJ-1003",
        "Dhanbad Pipeline Repair",
        "GAIL India",
        "Dhanbad, Jharkhand",
        Project.Status.PLANNED,
        Project.MeasurementSheetStatus.NOT_SUBMITTED,
        12,
        "Pipeline section repair",
    ),
    (
        "PRJ-1004",
        "Bokaro Warehouse Civil Work",
        "Bokaro Steel City Ltd",
        "Bokaro, Jharkhand",
        Project.Status.COMPLETED,
        Project.MeasurementSheetStatus.SUBMITTED,
        30,
        "Civil construction",
    ),
    (
        "PRJ-1005",
        "Hazaribagh Road Upgrade",
        "PWD Jharkhand",
        "Hazaribagh, Jharkhand",
        Project.Status.DRAFT,
        Project.MeasurementSheetStatus.NOT_SUBMITTED,
        20,
        "Road widening",
    ),
    (
        "PRJ-1006",
        "Office Complex Wiring Audit",
        "Mecon Limited",
        "Ranchi, Jharkhand",
        Project.Status.CANCELLED,
        Project.MeasurementSheetStatus.NOT_SUBMITTED,
        6,
        "Wiring safety audit",
    ),
]

TOOLS = [
    ("T-101", "Rotary Hammer Drill", "Power Tools"),
    ("T-102", "Angle Grinder", "Power Tools"),
    ("T-103", "Circular Saw", "Power Tools"),
    ("T-104", "Impact Wrench", "Power Tools"),
    ("T-105", "Claw Hammer", "Hand Tools"),
    ("T-106", "Adjustable Wrench Set", "Hand Tools"),
    ("T-107", "Screwdriver Kit", "Hand Tools"),
    ("T-108", "Spirit Level 24in", "Hand Tools"),
    ("T-109", "Ladder 12ft Aluminium", "Site Equipment"),
    ("T-110", "Concrete Mixer", "Heavy Equipment"),
    ("T-111", "Welding Machine", "Heavy Equipment"),
    ("T-112", "Cutting Torch Set", "Heavy Equipment"),
    ("T-113", "Multimeter", "Testing Equipment"),
    ("T-114", "Clamp Meter", "Testing Equipment"),
    ("T-115", "Torque Wrench", "Hand Tools"),
]

PPE_ITEMS = [
    ("PPE-201", PPE.PPEType.HELMET, "Safety Helmet White", "Free"),
    ("PPE-202", PPE.PPEType.HELMET, "Safety Helmet Yellow", "Free"),
    ("PPE-203", PPE.PPEType.SHOES, "Steel Toe Safety Shoes", "9"),
    ("PPE-204", PPE.PPEType.SHOES, "Steel Toe Safety Shoes", "10"),
    ("PPE-205", PPE.PPEType.GLOVES, "Leather Work Gloves", "L"),
    ("PPE-206", PPE.PPEType.JACKET, "Reflective Safety Jacket", "XL"),
    ("PPE-207", PPE.PPEType.HARNESS, "Full Body Harness", "Standard"),
    ("PPE-208", PPE.PPEType.GOGGLES, "Clear Safety Goggles", "Free"),
    ("PPE-209", PPE.PPEType.EAR_PROTECTION, "Ear Muffs", "Free"),
    ("PPE-210", PPE.PPEType.GLOVES, "Rubber Insulated Gloves", "L"),
    ("PPE-211", PPE.PPEType.HELMET, "Safety Helmet Blue", "Free"),
    ("PPE-212", PPE.PPEType.SHOES, "Rubber Gum Boots", "11"),
]

VEHICLES = [
    ("VEH-01", "JH05AB1234", Vehicle.VehicleType.TRUCK, "Tata 407 Gold"),
    ("VEH-02", "JH05CD5678", Vehicle.VehicleType.PICKUP, "Mahindra Bolero Pickup"),
    ("VEH-03", "JH01EF9012", Vehicle.VehicleType.VAN, "Maruti Eeco Cargo"),
    ("VEH-04", "JH09GH3456", Vehicle.VehicleType.BUS, "Force Traveller 26"),
    ("VEH-05", "JH02IJ7890", Vehicle.VehicleType.CAR, "Hyundai Aura"),
]


class Command(BaseCommand):
    help = "Seed realistic demo data for development."

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(42)
        today = date.today()

        admin = self._ensure_admin()
        workers = self._ensure_workers()
        projects = self._ensure_projects()
        tools = self._ensure_tools(today)
        ppe_items = self._ensure_ppe(today)
        vehicles = self._ensure_vehicles()

        self._seed_project_assignments(projects, workers)
        self._seed_tool_lifecycle(admin, tools, workers, projects, today)
        self._seed_ppe_lifecycle(admin, ppe_items, workers, today)
        self._seed_vehicle_assignments(admin, vehicles, workers, projects)

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully."))
        self.stdout.write("")
        self.stdout.write("Development credentials (DO NOT USE IN PRODUCTION):")
        self.stdout.write(f"  Admin login : mobile={ADMIN_MOBILE}  password={ADMIN_PASSWORD}")
        self.stdout.write(
            f"  Workers     : mobile=<worker's phone number>  password={WORKER_PASSWORD}"
        )

    # ------------------------------------------------------------------
    def _ensure_admin(self):
        user, created = User.objects.get_or_create(
            mobile_number=ADMIN_MOBILE,
            defaults={
                "role": User.Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "email": "admin@example.com",
            },
        )
        if created:
            user.set_password(ADMIN_PASSWORD)
            user.save()
        elif not user.check_password(ADMIN_PASSWORD):
            user.set_password(ADMIN_PASSWORD)
            user.save(update_fields=["password"])
        return user

    def _ensure_workers(self):
        profiles = []
        for employee_id, full_name, phone, designation in WORKERS:
            user = User.objects.filter(mobile_number=phone).first()
            if not user:
                user = User(
                    mobile_number=phone,
                    role=User.Role.WORKER,
                    first_name=full_name.split()[0],
                )
                user.set_password(WORKER_PASSWORD)
                user.save()
            profile, created = WorkerProfile.objects.get_or_create(
                employee_id=employee_id,
                defaults={
                    "user": user,
                    "full_name": full_name,
                    "phone_number": phone,
                    "designation": designation,
                    "employment_status": (
                        WorkerProfile.EmploymentStatus.INACTIVE
                        if employee_id == "EMP008"
                        else WorkerProfile.EmploymentStatus.ACTIVE
                    ),
                },
            )
            # If profile existed but was linked to a different user, link the new one.
            if profile.user != user:
                profile.user = user
                profile.save(update_fields=["user"])
            profiles.append(profile)
        return profiles

    def _ensure_projects(self):
        projects = []
        base = timezone.now() - timedelta(days=60)
        for idx, (
            number,
            name,
            client,
            location,
            status,
            sheet,
            manpower,
            job,
        ) in enumerate(PROJECTS):
            project, _ = Project.objects.get_or_create(
                project_number=number,
                defaults={
                    "project_name": name,
                    "client_name": client,
                    "location": location,
                    "description": f"Demo project: {name}.",
                    "start_date": (base + timedelta(days=idx * 5)).date(),
                    "expected_completion_date": (base + timedelta(days=180 + idx * 5)).date(),
                    "permit_no": f"PER-{2026}-{1000 + idx}",
                    "total_manpower": manpower,
                    "job": job,
                    "measurement_sheet_status": sheet,
                    "status": status,
                    "notes": "Seeded demo record.",
                },
            )
            projects.append(project)
        return projects

    def _ensure_tools(self, today):
        tools = []
        conditions = [
            Tool.Condition.EXCELLENT,
            Tool.Condition.GOOD,
            Tool.Condition.FAIR,
        ]
        for idx, (code, name, category) in enumerate(TOOLS):
            tool, created = Tool.objects.get_or_create(
                tool_id=code,
                defaults={
                    "name": name,
                    "category": category,
                    "description": f"Seeded demo tool {name}.",
                    "purchase_date": today - timedelta(days=200 + idx * 13),
                    "condition": conditions[idx % len(conditions)],
                },
            )
            tools.append(tool)
        return tools

    def _ensure_ppe(self, today):
        items = []
        for idx, (code, ppe_type, name, size) in enumerate(PPE_ITEMS):
            item, _ = PPE.objects.get_or_create(
                ppe_id=code,
                defaults={
                    "ppe_type": ppe_type,
                    "name": name,
                    "category": "Personal Protective Equipment",
                    "size": size,
                    "purchase_date": today - timedelta(days=150 + idx * 9),
                    "expiry_date": today + timedelta(days=(365 if idx % 3 else -30)),
                    "condition": PPE.Condition.GOOD if idx != 10 else PPE.Condition.DAMAGED,
                    "availability_status": (
                        PPE.AvailabilityStatus.AVAILABLE
                        if idx != 10
                        else PPE.AvailabilityStatus.DAMAGED
                    ),
                },
            )
            items.append(item)
        return items

    def _ensure_vehicles(self):
        vehicles = []
        today = timezone.localdate()
        for code, reg, vtype, model in VEHICLES:
            vehicle, _ = Vehicle.objects.get_or_create(
                vehicle_id=code,
                defaults={
                    "registration_number": reg,
                    "vehicle_type": vtype,
                    "make_model": model,
                    "capacity": "2 tons" if vtype == Vehicle.VehicleType.TRUCK else "",
                    "insurance_valid_until": today + timedelta(days=120),
                    "inspection_valid_until": today + timedelta(days=60),
                    "remarks": "Seeded demo vehicle.",
                },
            )
            vehicles.append(vehicle)
        return vehicles

    def _seed_project_assignments(self, projects, workers):
        pairs = [
            (0, [0, 1, 2]),
            (1, [3, 4]),
            (3, [0, 5]),
        ]
        for project_idx, worker_indices in pairs:
            project = projects[project_idx]
            for wi in worker_indices:
                ProjectWorker.objects.get_or_create(
                    project=project, worker=workers[wi], is_active=True
                )

    def _seed_tool_lifecycle(self, admin, tools, workers, projects, today):
        # Historical (returned) assignment for tool T-101 -> shows history.
        drill = tools[0]
        if not drill.assignments.exists():
            past = ToolAssignment.objects.create(
                tool=drill,
                worker=workers[1],
                project=projects[0],
                issue_date=today - timedelta(days=30),
                expected_return_date=today - timedelta(days=10),
                return_date=today - timedelta(days=12),
                issue_condition=Tool.Condition.GOOD,
                return_condition=Tool.Condition.FAIR,
                status=ToolAssignment.Status.RETURNED,
                remarks="Seeded historical assignment.",
            )
            record_audit(action="TOOL_ISSUED", entity=past, actor=admin)
            record_audit(action="TOOL_RETURNED", entity=past, actor=admin)

        # Active assignments.
        active_plan = [
            (tools[1], workers[0], projects[0]),
            (tools[2], workers[2], projects[0]),
            (tools[10], workers[3], None),
        ]
        for tool, worker, project in active_plan:
            if (
                tool.availability_status == Tool.AvailabilityStatus.AVAILABLE
                and not tool.assignments.filter(status=ToolAssignment.Status.ACTIVE).exists()
            ):
                assignment = ToolAssignment.objects.create(
                    tool=tool,
                    worker=worker,
                    project=project,
                    issue_date=today - timedelta(days=5),
                    expected_return_date=today + timedelta(days=25),
                    issue_condition=tool.condition,
                )
                tool.availability_status = Tool.AvailabilityStatus.ASSIGNED
                tool.save(update_fields=["availability_status"])
                record_audit(action="TOOL_ISSUED", entity=assignment, actor=admin)

        # One damaged tool with damage record (T-111 welding machine alternative).
        damaged = tools[13]  # Clamp Meter
        if not damaged.damages.exists():
            ToolDamage.objects.create(
                tool=damaged,
                damage_date=today - timedelta(days=3),
                damage_description="Dropped from ladder; casing cracked.",
                damage_condition=Tool.Condition.DAMAGED,
                repair_status=ToolDamage.RepairStatus.IN_PROGRESS,
            )
            damaged.availability_status = Tool.AvailabilityStatus.DAMAGED
            damaged.save(update_fields=["availability_status"])
            record_audit(
                action="TOOL_DAMAGED",
                entity_type="ToolDamage",
                entity_id=str(damaged.pk),
                actor=admin,
            )

    def _seed_ppe_lifecycle(self, admin, ppe_items, workers, today):
        plan = [
            (ppe_items[0], workers[0]),
            (ppe_items[2], workers[1]),
            (ppe_items[5], workers[2]),
        ]
        for item, worker in plan:
            if (
                item.availability_status == PPE.AvailabilityStatus.AVAILABLE
                and not item.assignments.filter(status=PPEAssignment.Status.ACTIVE).exists()
            ):
                assignment = PPEAssignment.objects.create(
                    ppe=item,
                    worker=worker,
                    issue_date=today - timedelta(days=20),
                    expected_return_date=None,
                    issue_condition=item.condition,
                )
                item.availability_status = PPE.AvailabilityStatus.ASSIGNED
                item.save(update_fields=["availability_status"])
                record_audit(action="PPE_ISSUED", entity=assignment, actor=admin)

        # Returned history for PPE-203.
        returned_item = ppe_items[2]
        has_history = returned_item.assignments.exclude(status=PPEAssignment.Status.ACTIVE).exists()
        if not has_history:
            hist = PPEAssignment.objects.create(
                ppe=returned_item,
                worker=workers[4],
                issue_date=today - timedelta(days=90),
                expected_return_date=today - timedelta(days=50),
                return_date=today - timedelta(days=52),
                issue_condition=PPE.Condition.GOOD,
                return_condition=PPE.Condition.POOR,
                status=PPEAssignment.Status.RETURNED,
                remarks="Returned worn out.",
            )
            record_audit(action="PPE_ISSUED", entity=hist, actor=admin)
            record_audit(action="PPE_RETURNED", entity=hist, actor=admin)

    def _seed_vehicle_assignments(self, admin, vehicles, workers, projects):
        driver_worker = next(w for w in workers if w.designation == "Driver")
        open_assignment = vehicles[0].assignments.filter(end_datetime__isnull=True).exists()
        if not open_assignment:
            start = timezone.now().replace(hour=8, minute=0, second=0, microsecond=0)
            VehicleAssignment.objects.create(
                vehicle=vehicles[0],
                worker=driver_worker,
                project=projects[0],
                driver=driver_worker,
                assignment_type=VehicleAssignment.AssignmentType.PROJECT,
                start_datetime=start - timedelta(days=2),
                purpose="Material delivery to Ranchi Tower site.",
            )
            vehicles[0].status = Vehicle.Status.IN_USE
            vehicles[0].save(update_fields=["status"])
            record_audit(
                action="VEHICLE_ASSIGNED",
                entity_type="VehicleAssignment",
                entity_id=str(vehicles[0].pk),
                actor=admin,
            )

        if not vehicles[2].assignments.exists():
            start = timezone.now() - timedelta(days=10)
            VehicleAssignment.objects.create(
                vehicle=vehicles[2],
                driver=driver_worker,
                assignment_type=VehicleAssignment.AssignmentType.GENERAL_USE,
                start_datetime=start,
                end_datetime=start + timedelta(days=4),
                purpose="Office supply runs.",
            )
            record_audit(
                action="VEHICLE_ASSIGNED",
                entity_type="VehicleAssignment",
                entity_id=str(vehicles[2].pk),
                actor=admin,
            )
