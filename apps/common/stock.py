"""Aggregations shared by the stock summary endpoints.

The tools, PPE and vehicles stock pages all need the same shape: item counts
broken down by one or more grouping fields, with a per-status split inside
each group. Doing it here keeps the three views thin and guarantees they
return the same payload structure.
"""

from django.db.models import Count

# Shown instead of an empty grouping value, so uncategorised stock still
# appears in the breakdown rather than silently disappearing.
UNGROUPED = "Uncategorised"


def status_breakdown(
    queryset,
    group_field,
    status_field,
    status_labels=None,
    statuses=None,
):
    """Group `queryset` by `group_field` and split each group by status.

    Runs a single aggregate query and pivots in Python, so a stock page with
    three groupings costs three cheap queries rather than one per group.

    `statuses` seeds every group with a zero for each known status, which keeps
    the payload shape stable: a client can render all the status chips without
    probing for keys, and a group with nothing assigned reports
    ``ASSIGNED: 0`` instead of omitting the field entirely.

    Note the per-status keys inside a group are the raw model choice values
    (``AVAILABLE``, ``IN_USE``, ...) because that is what the list endpoints
    already return in ``availability_status`` / ``status``. The lowercase keys
    on the flat part of the payload are legacy and are left alone.

    Returns a list ordered by descending total then label::

        [{"key": "HELMET", "label": "Safety Helmet", "total": 12,
          "AVAILABLE": 7, "ASSIGNED": 3, "DAMAGED": 1, "EXPIRED": 0,
          "RETIRED": 1}]
    """

    status_labels = status_labels or {}
    statuses = list(statuses or [])
    buckets = {}

    rows = queryset.values(group_field, status_field).annotate(count=Count("id")).order_by()
    for row in rows:
        raw_group = row[group_field]
        key = str(raw_group).strip() if raw_group not in (None, "") else UNGROUPED
        status = str(row[status_field])
        if key not in buckets:
            # Every group starts with the same keys, all zeroed.
            buckets[key] = {
                "key": key,
                "label": status_labels.get(key, key),
                "total": 0,
                **{s: 0 for s in statuses},
            }
        bucket = buckets[key]
        bucket[status] = bucket.get(status, 0) + row["count"]
        bucket["total"] += row["count"]

    groups = sorted(buckets.values(), key=lambda g: (-g["total"], g["label"]))
    return groups


def nest_breakdown(groups, sub_buckets, sub_key="sub_groups"):
    """Attach a secondary breakdown to each group.

    Used for PPE, where the size split only makes sense *inside* a type: the
    question is not "how many size 7 items are there" but "of the 20 safety
    shoes, how many are size 7". ``sub_buckets`` maps a group's ``key`` to the
    list of sub-groups for that group, as produced by a second
    ``status_breakdown`` call.

    Sub-groups are only attached when they exist, so a group with no size
    recorded stays a flat row instead of carrying an empty list.
    """

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
):
    """Build ``status_breakdown`` for `outer_field` with a nested `inner_field`.

    Two aggregate queries in total: one for the outer groups and one for the
    inner ones, then the inner rows are distributed to their parent. The
    nested payload stays consistent with the flat one because both come from
    the same zero-seeded status keys.

    Sub-groups land under ``inner_key`` on each parent group, and only when the
    group actually has items in it.
    """

    outer = status_breakdown(queryset, outer_field, status_field, outer_labels, statuses)
    inner = _inner_breakdown(queryset, outer_field, inner_field, status_field, statuses)
    return nest_breakdown(outer, inner, inner_key)


def _inner_breakdown(queryset, outer_field, inner_field, status_field, statuses):
    """Group by (outer, inner) and return {outer_key: [sub-group, ...]}."""

    buckets = {}
    rows = (
        queryset.values(outer_field, inner_field, status_field)
        .annotate(count=Count("id"))
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
        sub[status] = sub.get(status, 0) + row["count"]
        sub["total"] += row["count"]

    return {
        outer_key: sorted(subs.values(), key=lambda s: (-s["total"], s["label"]))
        for outer_key, subs in buckets.items()
    }
