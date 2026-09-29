"""Stock summary breakdowns for tools, PPE and vehicles.

The flat totals on these endpoints predate the stock screen; these tests cover
the `groups` / `size_groups` / `category_groups` breakdowns that page renders.
"""

from django.test import TestCase

from apps.ppe.models import PPE
from apps.tools.models import Tool
from apps.transportation.models import Vehicle
from tests.utils import BaseAPITestCase

TOOL_STOCK = "/api/v1/tools/stock/"
PPE_STOCK = "/api/v1/ppe/stock/"
VEHICLE_STOCK = "/api/v1/vehicles/stock/"

STATUS_URLS = (TOOL_STOCK, PPE_STOCK, VEHICLE_STOCK)


def group_by_key(groups):
    return {g["key"]: g for g in groups}


class ToolStockSummaryTests(BaseAPITestCase):
    def test_groups_break_down_by_category(self):
        Tool.objects.create(tool_id="T1", name="Hammer", category="Hand Tools")
        Tool.objects.create(tool_id="T2", name="Spanner", category="Hand Tools")
        Tool.objects.create(
            tool_id="T3",
            name="Drill",
            category="Power Tools",
            availability_status=Tool.AvailabilityStatus.ASSIGNED,
        )
        Tool.objects.create(
            tool_id="T4",
            name="Rod",
            category="Hand Tools",
            availability_status=Tool.AvailabilityStatus.DAMAGED,
        )

        response = self.admin_client.get(TOOL_STOCK)
        self.assertEqual(response.status_code, 200)
        data = response.data
        # The pre-existing flat totals still work.
        self.assertEqual(data["total"], 4)
        self.assertEqual(data["available"], 2)
        self.assertEqual(data["assigned"], 1)
        self.assertEqual(data["damaged"], 1)

        groups = group_by_key(data["groups"])
        self.assertEqual(groups["Hand Tools"]["total"], 3)
        self.assertEqual(groups["Hand Tools"][Tool.AvailabilityStatus.AVAILABLE], 2)
        self.assertEqual(groups["Hand Tools"][Tool.AvailabilityStatus.DAMAGED], 1)
        self.assertEqual(groups["Power Tools"]["total"], 1)
        self.assertEqual(groups["Power Tools"][Tool.AvailabilityStatus.ASSIGNED], 1)
        # Every known status is present, so the client can render fixed chips.
        self.assertEqual(groups["Power Tools"][Tool.AvailabilityStatus.LOST], 0)
        # Largest group first.
        self.assertEqual(data["groups"][0]["key"], "Hand Tools")

    def test_uncategorised_tools_are_reported_not_dropped(self):
        Tool.objects.create(tool_id="T1", name="Mystery", category="")
        response = self.admin_client.get(TOOL_STOCK)
        groups = group_by_key(response.data["groups"])
        self.assertIn("Uncategorised", groups)
        self.assertEqual(groups["Uncategorised"]["total"], 1)
        self.assertEqual(sum(g["total"] for g in response.data["groups"]), 1)

    def test_group_totals_always_match_the_total(self):
        for i in range(3):
            Tool.objects.create(tool_id=f"A{i}", name="A", category="X")
        for i in range(2):
            Tool.objects.create(tool_id=f"B{i}", name="B", category="Y")
        Tool.objects.create(tool_id="C0", name="C", category="")
        data = self.admin_client.get(TOOL_STOCK).data
        self.assertEqual(sum(g["total"] for g in data["groups"]), data["total"])


class PPEStockSummaryTests(BaseAPITestCase):
    def test_groups_break_down_by_type(self):
        PPE.objects.create(ppe_id="P1", name="Helmet", ppe_type=PPE.PPEType.HELMET)
        PPE.objects.create(ppe_id="P2", name="Helmet 2", ppe_type=PPE.PPEType.HELMET)
        PPE.objects.create(ppe_id="P3", name="Gloves", ppe_type=PPE.PPEType.GLOVES)

        data = self.admin_client.get(PPE_STOCK).data
        groups = group_by_key(data["groups"])
        self.assertEqual(groups[PPE.PPEType.HELMET]["total"], 2)
        # The human label is resolved from the choices, not the raw code.
        self.assertEqual(groups[PPE.PPEType.HELMET]["label"], "Safety Helmet")
        self.assertEqual(groups[PPE.PPEType.GLOVES]["label"], "Gloves")
        self.assertEqual(sum(g["total"] for g in data["groups"]), data["total"])

    def test_size_groups_break_down_by_size(self):
        PPE.objects.create(ppe_id="P1", name="Helmet", ppe_type=PPE.PPEType.HELMET, size="M")
        PPE.objects.create(ppe_id="P2", name="Helmet", ppe_type=PPE.PPEType.HELMET, size="L")
        PPE.objects.create(ppe_id="P3", name="Helmet", ppe_type=PPE.PPEType.HELMET, size="L")
        PPE.objects.create(
            ppe_id="P4",
            name="Gloves",
            ppe_type=PPE.PPEType.GLOVES,
            size="M",
            availability_status=PPE.AvailabilityStatus.ASSIGNED,
        )

        data = self.admin_client.get(PPE_STOCK).data
        sizes = group_by_key(data["size_groups"])
        self.assertEqual(sizes["L"]["total"], 2)
        self.assertEqual(sizes["L"][PPE.AvailabilityStatus.AVAILABLE], 2)
        # Sizes are independent of PPE type, so M spans two types.
        self.assertEqual(sizes["M"]["total"], 2)
        self.assertEqual(sizes["M"][PPE.AvailabilityStatus.ASSIGNED], 1)
        self.assertEqual(sum(g["total"] for g in data["size_groups"]), data["total"])

    def test_blank_size_is_reported_as_unspecified_bucket(self):
        PPE.objects.create(ppe_id="P1", name="Helmet", ppe_type=PPE.PPEType.HELMET)
        data = self.admin_client.get(PPE_STOCK).data
        sizes = group_by_key(data["size_groups"])
        self.assertEqual(sizes["Uncategorised"]["total"], 1)
        self.assertEqual(sum(g["total"] for g in data["size_groups"]), data["total"])

    def test_sizes_are_nested_inside_each_type(self):
        """The useful question is "of these 20 shoes, how many are size 7"."""
        for index in range(3):
            PPE.objects.create(
                ppe_id=f"SHOE{index}", name="Shoe", ppe_type=PPE.PPEType.SHOES, size="7"
            )
        for index in (4, 5):
            PPE.objects.create(
                ppe_id=f"SHOE{index}", name="Shoe", ppe_type=PPE.PPEType.SHOES, size="8"
            )
        PPE.objects.create(ppe_id="HELM1", name="Helmet", ppe_type=PPE.PPEType.HELMET, size="M")

        data = self.admin_client.get(PPE_STOCK).data
        groups = group_by_key(data["groups"])
        shoes = groups[PPE.PPEType.SHOES]
        self.assertEqual(shoes["total"], 5)

        sizes = group_by_key(shoes["sub_groups"])
        self.assertEqual(sizes["7"]["total"], 3)
        self.assertEqual(sizes["8"]["total"], 2)
        # Sub-groups are ordered biggest first.
        self.assertEqual(shoes["sub_groups"][0]["key"], "7")
        # Sub-group totals reconcile with their parent group.
        self.assertEqual(sum(s["total"] for s in shoes["sub_groups"]), shoes["total"])

        # Nesting is per type: the helmet's M is not folded into the shoes.
        helmet = groups[PPE.PPEType.HELMET]
        self.assertEqual(helmet["sub_groups"][0]["key"], "M")
        self.assertEqual(helmet["sub_groups"][0]["total"], 1)

    def test_nested_sizes_carry_their_own_status_split(self):
        PPE.objects.create(ppe_id="S1", name="Shoe", ppe_type=PPE.PPEType.SHOES, size="7")
        PPE.objects.create(
            ppe_id="S2",
            name="Shoe",
            ppe_type=PPE.PPEType.SHOES,
            size="7",
            availability_status=PPE.AvailabilityStatus.ASSIGNED,
        )
        data = self.admin_client.get(PPE_STOCK).data
        shoes = group_by_key(data["groups"])[PPE.PPEType.SHOES]
        size7 = group_by_key(shoes["sub_groups"])["7"]
        self.assertEqual(size7[PPE.AvailabilityStatus.AVAILABLE], 1)
        self.assertEqual(size7[PPE.AvailabilityStatus.ASSIGNED], 1)

    def test_blank_size_nests_as_uncategorised(self):
        PPE.objects.create(ppe_id="G1", name="Gloves", ppe_type=PPE.PPEType.GLOVES, size="")
        data = self.admin_client.get(PPE_STOCK).data
        gloves = group_by_key(data["groups"])[PPE.PPEType.GLOVES]
        self.assertEqual(gloves["sub_groups"][0]["key"], "Uncategorised")
        self.assertEqual(gloves["sub_groups"][0]["total"], 1)

    def test_category_groups_use_the_free_text_category(self):
        PPE.objects.create(
            ppe_id="P1", name="Helmet", ppe_type=PPE.PPEType.HELMET, category="Site A"
        )
        PPE.objects.create(
            ppe_id="P2", name="Helmet", ppe_type=PPE.PPEType.HELMET, category="Site A"
        )
        PPE.objects.create(ppe_id="P3", name="Vest", ppe_type=PPE.PPEType.JACKET, category="Site B")
        data = self.admin_client.get(PPE_STOCK).data
        categories = group_by_key(data["category_groups"])
        self.assertEqual(categories["Site A"]["total"], 2)
        self.assertEqual(categories["Site B"]["total"], 1)

    def test_existing_flat_counts_are_unchanged(self):
        PPE.objects.create(ppe_id="P1", name="Helmet", ppe_type=PPE.PPEType.HELMET)
        PPE.objects.create(
            ppe_id="P2",
            name="Gloves",
            ppe_type=PPE.PPEType.GLOVES,
            availability_status=PPE.AvailabilityStatus.ASSIGNED,
        )
        data = self.admin_client.get(PPE_STOCK).data
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["available"], 1)
        self.assertEqual(data["assigned"], 1)
        self.assertEqual(data["condition_good"], 2)


class VehicleStockSummaryTests(BaseAPITestCase):
    def test_groups_break_down_by_vehicle_type(self):
        Vehicle.objects.create(
            vehicle_id="V1",
            registration_number="JH-01-0001",
            vehicle_type=Vehicle.VehicleType.TRUCK,
        )
        Vehicle.objects.create(
            vehicle_id="V2",
            registration_number="JH-01-0002",
            vehicle_type=Vehicle.VehicleType.TRUCK,
            status=Vehicle.Status.IN_USE,
        )
        Vehicle.objects.create(
            vehicle_id="V3",
            registration_number="JH-01-0003",
            vehicle_type=Vehicle.VehicleType.VAN,
        )

        data = self.admin_client.get(VEHICLE_STOCK).data
        groups = group_by_key(data["groups"])
        self.assertEqual(groups[Vehicle.VehicleType.TRUCK]["total"], 2)
        self.assertEqual(groups[Vehicle.VehicleType.TRUCK][Vehicle.Status.AVAILABLE], 1)
        self.assertEqual(groups[Vehicle.VehicleType.TRUCK][Vehicle.Status.IN_USE], 1)
        self.assertEqual(groups[Vehicle.VehicleType.TRUCK]["label"], "Truck")
        self.assertEqual(groups[Vehicle.VehicleType.VAN]["total"], 1)
        self.assertEqual(sum(g["total"] for g in data["groups"]), data["total"])
        # The pre-existing flat type counters are still present.
        self.assertEqual(data["truck"], 2)
        self.assertEqual(data["van"], 1)


class StockPermissionTests(TestCase):
    """Stock is admin-only; a plain worker must not see fleet-wide counts."""

    def setUp(self):
        self.base = BaseAPITestCase()
        self.base.setUp()

    def test_worker_cannot_read_stock_summaries(self):
        for url in STATUS_URLS:
            response = self.base.worker_client.get(url)
            self.assertEqual(response.status_code, 403, url)
