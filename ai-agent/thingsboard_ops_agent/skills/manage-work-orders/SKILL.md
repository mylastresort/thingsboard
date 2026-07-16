---
name: manage-work-orders
description: Manage work order lifecycle for industrial assets. Use when the user wants to list, create, approve, assign, close, or cancel work orders, view work order KPIs, costs, schedules, or technician assignments.
---

# Manage Work Orders

Goal: handle work order operations through the `wo_agent` specialist, which
backs onto a CouchDB work-order store with Maximo-style field names.

## Steps

1. **List work orders**: Call `wo_agent` with `list_workorders`. Filter by
   `site_id`, `status` (OPEN / APPROVED_PENDING), `asset_num`, `priority`,
   or date range. Use `page_size=0` to get all matches in one call.

2. **Get details**: For a specific work order, call `get_workorder` with the
   `wonum` and `site_id`. To see child tasks, use `get_workorder_tasks`.

3. **Costs & variance**: Call `get_workorder_costs` for labor/material/service
   breakdown, or `get_workorder_actuals_vs_planned` for estimated-vs-actual
   hours and cost variance.

4. **KPIs**: Call `get_workorder_kpis` with a `site_id` and `period_months`
   (default 3) for site-level metrics: totals, backlog, overdue, avg
   completion, priority/asset breakdowns.

5. **Schedule**: Call `get_schedule_calendar` for a date window to see
   scheduled (non-terminal) work orders bucketed by day.

6. **Technician view**: Call `get_my_assigned_workorders` with a `labor_code`
   to see what a specific technician has assigned.

7. **Create**: Call `generate_work_order` with `description`, `asset_num`,
   `site_id`, and optional `priority`, `work_type`, `reported_by`, `location`,
   `notes`. Status starts as WAPPR (waiting approval).

8. **Lifecycle**: After creation, the typical flow is:
   - `approve_workorder` (WAPPR -> APPR)
   - `assign_technician` (APPR -> adds wplabor line)
   - `close_workorder` (-> COMP, with actual_hours and resolution_notes)
   - Or `cancel_workorder` (-> CAN) with a reason.

9. **Update**: Call `update_workorder` to change description, priority,
   location, asset, notes, or failure_code.

Always confirm the `site_id` before mutations. If the user doesn't specify
a site, list available sites via `iot_sensor_agent` (tool: `sites`) first,
or ask for clarification.
