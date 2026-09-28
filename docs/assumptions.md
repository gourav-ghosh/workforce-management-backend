# Implementation Assumptions — Version 1.2

Where the PRD/TRD left room for interpretation, the smallest reasonable
implementation was chosen. Each assumption below is documented so it can be
confirmed or revised during acceptance.

## Authentication

1. **Login identifier**: mobile number + password. The legacy Django
   `username` field is retained for compatibility but is not used to log in.
2. **Password reset delivery**: email-based reset works for accounts that
   have an email address (admins). Workers typically have no email on file,
   so admins reset worker passwords through the dedicated
   `POST /workers/{id}/reset-password/` endpoint. The request endpoint always
   answers generically to avoid account enumeration.
3. Setting a worker's employment status to `INACTIVE` also deactivates their
   login account.

## Workers

4. Creating a worker always creates the linked login account; `mobile_number`
   and `password` are required fields on creation (returned nowhere; chosen by
   the admin at creation time).
5. Deleting a worker is blocked when any assignment history exists; the
   intended offboarding path is setting employment status to `INACTIVE`.

## Projects

6. `project_plan` accepts common document formats (PDF/Office/images); V1
   exposes upload + URL only (view/download/share UI was commented out of
   the PRD scope).
7. Project deletion is blocked while assignment history exists (protects
   PRD-required history retention).

## Tools

8. Tool damage recorded while a tool is issued does not auto-close the open
   assignment; the tool status becomes `DAMAGED` (blocking re-issue) and the
   normal return flow closes the assignment later.
9. After a return, tool condition drives availability: returning with
   condition `DAMAGED` keeps the tool unavailable; otherwise it becomes
   `AVAILABLE`.
10. Manual status transitions (`set-status`) are provided for maintenance /
    lost / retired states which have no dedicated workflow in V1.

## PPE

11. One active assignment per PPE item (unit-based tracking), matching the
    TRD's default rule. "Attention" = expired by date or damaged/expired
    status.

## Transportation

12. Assigning an `AVAILABLE` vehicle marks it `IN_USE` immediately, even for
    future-dated assignments (V1 has no scheduler); unassignment restores
    `AVAILABLE` when no other current assignment remains.
13. An assignment needs context: project, worker/driver or purpose must be
    present (TRD §7 business rule).
14. Overlap prevention treats an open-ended assignment as blocking all later
    starts until it is closed.

## Dashboard

15. "Tools requiring attention" = DAMAGED / UNDER_MAINTENANCE / LOST.
16. "PPE requiring attention" = expired by date OR status damaged/expired.
17. Worker home uses `GET /me/summary/` (counts of own assignments) instead
    of the org-wide dashboard, which stays admin-only.

## Out of scope (explicitly excluded per PRD)

- Notifications/alerts, reports & PDF generation (commented out of the
  approved PRD scope), web admin dashboard, payroll/attendance, GPS,
  offline-first, QR scanning, integrations, multi-tenancy.
