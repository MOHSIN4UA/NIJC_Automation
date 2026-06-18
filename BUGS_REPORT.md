# NIJC Admin Portal — Manage Appointments Bug Report

**Date:** 2026-06-04
**Environment:** https://qa-admin.azurehosted.app
**Module:** Scheduling → Manage Appointments
**Reporter:** Test automation suite (`tests/test_manage_appointment.py`)
**Verified by:** Manual browser reproduction + Playwright MCP

---

## BUG-001 — Date filter day-window is timezone-shifted

**Severity:** High
**Detected by test cases:** TC_023, TC_024, TC_052
**Code references:**
- [test_tc_cal_023_from_date_boundary_inclusive](tests/test_manage_appointment.py#L1202)
- [test_tc_cal_024_to_date_boundary_inclusive](tests/test_manage_appointment.py#L1280)
- [test_tc_cal_052_single_day_date_range](tests/test_manage_appointment.py#L2230)

### Description
The "Date & Time" filter on Manage Appointments uses a day-window that does
not align with the office's local timezone. Afternoon appointments on date
`D` are bucketed into the `D+1` filter; querying `D` alone misses them.

### Reproduction
1. Login as admin → Manage Appointments → click **Reset**.
2. Set **From** = `06/05/2026` and **To** = `06/05/2026` (single-day filter on Jun 5).
3. Wait ~3 seconds for the table to refresh.
4. Scroll through every page of results and note every Date & Time.

### Expected
Only `Fri Jun 5, 2026` rows are returned (all hours).

### Actual
35 rows returned:
- **25 Jun 4 PM rows leak in** (times 01:40 PM, 02:20 PM, 03:00 PM, 03:40 PM, 04:20 PM)
- **10 Jun 5 AM rows** present (09:00 AM, 09:40 AM, 12:00 PM)
- **0 Jun 5 PM rows** — completely missing despite being on the filter date

### Reverse direction (TC_024 shape)
Filter **From** = `05/26/2026`, **To** = `06/05/2026`:
- Page 1: 50 Jun 4 rows
- Page 2: 2 Jun 4 + 9 Jun 5 AM rows only (no Jun 5 afternoon)

### Root cause (suspected)
The backend appears to compare slot timestamps using UTC (or a non-office
timezone), so any local-time slot at or after ~13:00 EST on date `D` crosses
the UTC date boundary and is indexed as `D+1`.

### Impact
- Staff scheduling a same-day filter cannot see afternoon appointments.
- Daily/end-of-day reports under-count by ~half the day.
- Cross-day workarounds (`From = D, To = D+1`) over-count by including the
  next morning.

### Fix direction
The filter range must be applied in the **office's local timezone** for both
start-of-day and end-of-day, not UTC.

---

## BUG-002 — Employee role can edit Notes on unassigned appointments

**Severity:** High (role-gating / access control)
**Detected by test case:** TC_043
**Code reference:** [test_tc_cal_043_employee_cannot_edit_unassigned_notes](tests/test_manage_appointment.py#L1862)

### Description
A user with the **Employee** role can open an **unassigned** appointment's
Internal Notes dialog, type new content, and save it — even though the
spec requires read-only access for that role on rows the employee is not
assigned to.

### Reproduction
1. Sign in as `testqa-emp@immigrantjustice.org` (employee role).
2. Sidebar → Manage Appointments → click **Reset**.
3. Locate any row with **Status = Booked** and **Assigned to = empty**
   (e.g. `TC003-478508 ManageAppointment`).
4. Click the row's **⋮ Action** menu → **Notes**.
5. The "Internal Notes" dialog opens.
6. Click into the textarea and type any text.
7. Observe the **Save Note** button.

### Expected
At least one of:
- Notes option absent from menu, OR
- Notes option present but disabled, OR
- Textarea is read-only, OR
- Save Note button is disabled.

### Actual
- Notes option is **visible and enabled** in the action menu.
- Dialog opens normally.
- Textarea accepts input (verified by typing "notes enabled").
- **Save Note button is fully active** (green, clickable).

### Evidence
Manual screenshot captured 2026-06-04 — employee logged in (`test ga-emp`),
unassigned `TC003-478508` row, dialog open with editable textarea and active
Save Note.

### Impact
Employees can modify case notes on appointments they have no responsibility
for. Audit trail integrity compromised; potential PII handling concern.

### Fix direction
Server-side authorization must reject Notes write attempts from the Employee
role on rows where `assignedTo != currentUser`. UI should mirror this by
disabling Save or showing a read-only dialog.

---

## BUG-003 — Notes audit log is missing timestamp metadata

**Severity:** Medium
**Detected by test case:** TC_045
**Code reference:** [test_tc_cal_045_note_audit_log_visible](tests/test_manage_appointment.py#L1938)

### Description
When a note is saved on an appointment and the dialog is reopened, the
saved note displays the **author name** but does NOT display **when** the
note was created. There is no timestamp, no "5 min ago", no creation date.

### Reproduction
1. Sign in as admin.
2. Manage Appointments → pick any appointment → ⋮ → **Notes**.
3. Type a test note (e.g. "TC_045 audit-log probe") → click **Save Note**.
4. Wait 2 seconds; dialog may close.
5. Click the same row's ⋮ → **Notes** again to reopen.

### Expected
Each saved note shows BOTH:
- Author name (e.g. "test qa [null] [null]") — present ✓
- A timestamp or relative time (e.g. "12:45 PM", "Jun 4, 2026", "5 min ago") — **missing**

### Actual
- Author is displayed (an avatar + the saver's full name).
- **No timestamp visible anywhere** in the saved-note block.

### Evidence
Manual screenshot captured 2026-06-04 — admin saved "hello ur the best",
reopen shows author "test qa [null] [null]" but no creation time.

### Impact
- No way to tell when a note was written or if it predates a relevant event.
- Reduces case-audit trail integrity (notes can't be ordered or correlated
  to other timeline events).

### Fix direction
Render the note creation timestamp alongside the author. Format suggestions:
- Absolute (`Jun 4, 2026 12:45 PM EST`), or
- Relative (`5 minutes ago`) with a tooltip showing the absolute time.

---

## Pending verification (do NOT treat as confirmed bugs yet)

| Test | Hypothesis | Status |
|---|---|---|
| TC_046 | Employee role can see / use Approve and Reject actions (admin-only) | Failing in suite; manual MCP verification not yet done |
| TC_047 | Office filter list is not alphabetically sorted | Failing in suite; manual MCP verification not yet done |

Both will be added to this report only after live browser verification, per
the "no false reports" policy.

---

## Verification summary

| Bug | Verified in real browser? | Test case correctly detects? |
|---|---|---|
| BUG-001 (date filter) | ✓ Yes (MCP + manual confirmation) | ✓ Yes |
| BUG-002 (employee notes) | ✓ Yes (manual screenshot) | ✓ Yes |
| BUG-003 (note timestamp) | ✓ Yes (manual screenshot) | ✓ Yes (timestamp half), regex bug in author half |

---

## Notes for the dev team

- All three bugs are reproducible at the time of writing in
  https://qa-admin.azurehosted.app .
- The automated test suite (`pytest tests/test_manage_appointment.py`) will
  continue to hard-fail on these cases until the underlying app fixes land.
  This is intentional — the failing tests are the regression signal.
- BUG-002 and BUG-003 should be considered together: both relate to the
  internal-notes feature's role/audit gaps.
