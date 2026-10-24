"""Aggregations shared by the stock summary endpoints.

The tools, PPE and vehicles stock pages all need the same shape: item counts
broken down by one or more grouping fields, with a per-status split inside
each group. Doing it here keeps the three views thin and guarantees they
return the same payload structure.
"""

from django.db.models import Count, Sum

# Shown instead of an empty grouping value, so uncategorised stock still
# appears in the breakdown rather than silently disappearing.
UNGROUPED = "Uncategorised"


def status_breakdown(
    queryset,
    group_field,
    status_field,
    status_labels=None,
    statuses=None,
    quantity_field="total_quantity",
):
    """Group `queryset` by `group_field` and split each group by status.

    If `quantity_field` is provided and exists on the model, sums that field.
    Otherwise, counts records.
    """

    status_labels = status_labels or {}
    statuses = list(statuses or [])
    buckets = {}

    if quantity_field:
        try:
            queryset.model._meta.get_field(quantity_field)
            use_sum = True
        except Exception:
            use_sum = False
    else:
        use_sum = False

    if use_sum:
        rows = queryset.values(group_field, status_field).annotate(total=Sum(quantity_field)).order_by()
    else:
        rows = queryset.values(group_field, status_field).annotate(total=Count("id")).order_by()

    for row in rows:
        raw_group = row[group_field]
        key = str(raw_group).strip() if raw_group not in (None, "") else UNGROUPED
        status = str(row[status_field])
        if key not in buckets:
            buckets[key] = {
                "key": key,
                "label": status_labels.get(key, key),
                "total": 0,
                **{s: 0 for s in statuses},
            }
        bucket = buckets[key]
        bucket[status] = bucket.get(status, 0) + (row["total"] or 0)
        bucket["total"] += row["total"] or 0

    groups = sorted(buckets.values(), key=lambda g: (-g["total"], g["label"]))
    return groups


def nest_breakdown(groups, sub_buckets, sub_key="sub_groups"):
    """Attach a secondary breakdown to each group."""

    for group in groups:
        subs = sub_buckets.get(group["key"])
        if subs:
            group[sub_key] = subs
    return groups


def status_breakdown_by(
    queryset,
    outer_field,
    inner_field,
    status_field,
    outer_labels=None,
    statuses=None,
    inner_key="sub_groups",
    quantity_field="total_quantity",
):
    """Build `status_breakdown` for `outer_field` with a nested `inner_field`."""

    outer = status_breakdown(queryset, outer_field, status_field, outer_labels, statuses, quantity_field)
    inner = _inner_breakdown(queryset, outer_field, inner_field, status_field, statuses, quantity_field)
    return nest_breakdown(outer, inner, inner_key)


def _inner_breakdown(queryset, outer_field, inner_field, status_field, statuses, quantity_field="total_quantity"):
    """Group by (outer, inner) and return {outer_key: [sub-group, ...]}."""

    buckets = {}
    if quantity_field:
        try:
            queryset.model._meta.get_field(quantity_field)
            use_sum = True
        except Exception:
            use_sum = False
    else:
        use_sum = False

    if use_sum:
        rows = (
            queryset.values(outer_field, inner_field, status_field)
            .annotate(total=Sum(quantity_field))
            .order_by()
        )
    else:
        rows = (
            queryset.values(outer_field, inner_field, status_field)
            .annotate(total=Count("id"))
            .order_by()
        )
    for row in rows:
        raw_outer = row[outer_field]
        outer_key = str(raw_outer).strip() if raw_outer not in (None, "") else UNGROUPED
        raw_inner = row[inner_field]
        inner_key = str(raw_inner).strip() if raw_inner not in (None, "") else UNGROUPED
        status = str(row[status_field])
        subs = buckets.setdefault(outer_key, {})
        sub = subs.get(inner_key)
        if sub is None:
            sub = {
                "key": inner_key,
                "label": inner_key,
                "total": 0,
                **{s: 0 for s in (statuses or [])},
            }
            subs[inner_key] = sub
        sub[status] = sub.get(status, 0) + (row["total"] or 0)
        sub["total"] += row["total"] or 0

    return {
        outer_key: sorted(subs.values(), key=lambda s: (-s["total"], s["label"]))
        for outer_key, subs in buckets.items()
    }