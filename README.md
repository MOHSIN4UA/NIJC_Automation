# NIJC Automation

End-to-end regression suite for the **NIJC (National Immigrant Justice Center) admin portal** at `qa-admin.azurehosted.app`, built on Python + Playwright + pytest.

Three test files cover the three core scheduling modules: booking, managing appointments, and managing office calendars. Locators and configuration are externalised so behaviour is decoupled from selectors and credentials.

---

## Tech stack

| Layer | Tool |
|---|---|
| Language | Python 3.12 |
| Browser automation | [Playwright](https://playwright.dev/python) (`playwright`, `pytest-playwright`) |
| Test runner | pytest 7.4 |
| Reporting | `pytest-html` (self-contained HTML report) |
| Config | TOML (`conf.toml`, `xpath.toml`) |
| Persistent SSO | `user_data_dir` browser context (per-role cookies cached) |

---

## Repository layout

| Path | Purpose |
|---|---|
| [tests/test_book_appointment.py](tests/test_book_appointment.py) | Booking-flow regression — TC_001…TC_084 (marker: `book_appointment`) |
| [tests/test_manage_appointment.py](tests/test_manage_appointment.py) | Manage Appointments (list / calendar / filters / role gating) — TC_cal_001…TC_cal_116 (marker: `manage_appointment`) |
| [tests/test_manage_calendar.py](tests/test_manage_calendar.py) | Manage Calendars (calendar config, holidays, slot generation) — TC_001…TC_116 (marker: `manage_calendar`) |
| [tests/utils.py](tests/utils.py) | Shared helpers — booking flow, clock picker, save-and-wait, navigation |
| [tests/manage_calendar_config.toml](tests/manage_calendar_config.toml) | Calendar-suite-specific test data |
| [conftest.py](conftest.py) | Fixtures: `admin_session`, `employee_tab` (two-tab role switch), login resilience |
| [xpath.toml](xpath.toml) | Single source of truth for every selector — sections per page |
| [conf.toml](conf.toml) | URLs, credentials (admin / employee / aadmin), test data, timezone constants |
| [pytest.ini](pytest.ini) | Pytest config + markers |
| [BUGS_REPORT.md](BUGS_REPORT.md) | Manually-verified product defects detected by the suite |

---

## Setup

```bash
# 1. Create + activate a virtual env (Python 3.12+)
python3 -m venv .venv
source .venv/bin/activate

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install Playwright browsers
playwright install chromium

# 4. Provide credentials (edit conf.toml — see "Configuration" below)
```

The QA admin URL, admin/employee/aadmin email + password, and all test data live in [conf.toml](conf.toml). The suite reads from there at fixture-load time — never edit credentials into test files.

---

## Configuration — `conf.toml`

Key sections:

- `[admin]` — base URL, `manage_appointments_path`, `reschedule_appointment_path`, URL globs.
- `[credentials]` — `admin_email` / `admin_password`, `employee_email` / `employee_password`, `aadmin_email` / `aadmin_password`.
- `[new_calendar]` — default test office (Indianapolis, IN) used by the booking flow; includes operating hours, scheduled break, tea break, and slot duration.
- `[secondary_location]` — alternate office (Chicago, IL) for multi-office tests.
- `[manage_appointment]` — note limits, performance budgets, expected US timezone abbreviations.
- `[test_data]` — `target_user`, wide date filter range, reschedule day/time.
- `[playwright]` — headless toggle, viewport, default timeout.

Use absolute, ISO-like values when possible. Never hardcode dates or URLs in the test files — pull them from `conf.toml`.

---

## Locators — `xpath.toml`

All selectors — XPath, CSS, testid — live in [xpath.toml](xpath.toml), grouped by section (`[book_appointment]`, `[manage_appointment]`, `[manage_calendar]`, `[user_management]`, etc.). Tests reference them through the `xpaths` dict loaded by fixtures:

```python
page.locator(xpaths["search_input_apt"]).first.click()
```

**Rules:**
- New selectors go in `xpath.toml`. **Never** inline an `xpath=...` or CSS literal in a test or helper.
- Use stable testids when the app provides them (e.g. `qa-no-records-found`, `qa-confirm-conflict-reject`).
- Templated selectors use `{name}` placeholders, formatted at call site: `xpaths["office_card"].format(name=office_name)`.

---

## Running tests

### By marker
```bash
pytest -m book_appointment
pytest -m manage_appointment
pytest -m manage_calendar
```

### By name
```bash
pytest tests/test_book_appointment.py::test_tc_068_appointment_stores_original_slot_datetime
```

### A subset across files
```bash
pytest -k "test_tc_068 or test_tc_069 or test_tc_07"
```

## Generating reports

A self-contained HTML report is produced on **every** test run — the flags are already baked into [pytest.ini](pytest.ini) (`--html=... --self-contained-html`), so a bare `pytest` is enough. No extra setup is needed.

Each run writes a **uniquely-named, timestamped** file so runs don't overwrite each other:

```
report/test_report_<unix-timestamp>.html      e.g. report/test_report_1782710674.html
```

(The timestamp is appended in `pytest_configure` in [conftest.py](conftest.py).)

The report includes a per-test **Description** (from each test's docstring), a **timestamp** column, full **stdout / stderr / log output captured under each test**, and **screenshots embedded inline for any failing test** (see the hooks in [conftest.py](conftest.py)).

### Run a suite, then open the newest report
```bash
source .venv/bin/activate && pytest -m manage_calendar && xdg-open "$(ls -t report/*.html | head -1)"
```

Swap the scope for whatever you want to report on:
```bash
pytest                                   # whole suite
pytest -m book_appointment               # one module
pytest tests/test_manage_calendar.py     # one file
pytest "tests/test_manage_calendar.py::test_tc_cal_001_verify_dashboard_is_visible_after_login"  # one test
```

Open the most recent report in a browser:
```bash
xdg-open "$(ls -t report/*.html | head -1)"
```

> Capturing note: output logs appear in the report because `-s` is **not** used (with `-s`, `print()` streams to the console and never reaches the report). The trade-off is that console output is buffered per-test during a run — on a fresh login the live "approve MFA" prompt won't show until the test finishes. If you ever need to watch it live, add `-s` to that one invocation.

> `report/` and `*.html` are gitignored — reports are local build artifacts and are never committed.

---

## Fixtures

| Fixture | Scope | Use |
|---|---|---|
| `admin_session` | session | Returns `(page, xpaths, config)` logged in as `admin_email`. Handles SSO + session restoration. |
| `employee_tab` | context-manager | Inside `with employee_tab(admin_page, …) as emp_page:` opens a second tab as the **Employee** role (cached cookies, MFA-free on subsequent runs), restores admin cookies on exit. Used by role-gating tests (TC_043, TC_046, TC_071, TC_079, TC_080…). |
| `user_dashboard_session` | session | Logged-in **user/applicant** view for non-admin tests. |

Cookies for the employee role are cached to `employee_cookies.json` — first run requires MFA approval on the configured employee's phone; subsequent runs are MFA-free until the session expires. This file is in `.gitignore` and must never be committed.

---

## Common helpers (`tests/utils.py`)

| Helper | What it does |
|---|---|
| `_navigate_to_users(page, xpaths)` | Navigate to People Management → Users via the side menu. |
| `_open_book_from_users_list(page, xpaths, search_text)` | Open the Book Appointment screen for a specific user. |
| `_complete_booking_flow(page, xpaths, config, member_name=None, prefer_late_slot=False)` | End-to-end booking: member → service → office → date → slot → confirm → final book. Returns `{slot_text, date_iso}` for round-trip verification. |
| `_create_user_and_skip_eligibility(...)` | Seed a fresh user with valid eligibility for booking tests. |
| `_dismiss_booking_success_dialog(...)` | Close the post-booking confirmation dialog. |
| `_navigate_via_menu(page, xpaths, menu_key)` | Generic side-menu navigation. |
| `_ensure_manage_calendars_tab(...)` / `_ensure_holiday_tab(...)` | Switch between Calendars and Holidays sub-tabs. |
| `_wait_for_picker(...)` / `_select_date_in_picker(...)` | MUI DatePicker primitives. |
| `_click_save_and_wait(page, xpaths)` | Clicks Save / Update Configuration / Proceed, then waits for the progress bar to clear before checking the next UI (avoids reading stale state). |

The booking-flow tests TC_068+ add helpers in `tests/test_book_appointment.py`:
- `_seed_user_book_capture(page, xpaths, config, tc_id)` — seed + book + return captured slot metadata.
- `_find_appt_row_datetime(page, xpaths, config, full_name)` — search Manage Appointments and return the row's Date & Time cell text.
- `_widen_appts_filters(page, xpaths, config)` — set All Statuses + wide date range so historical/terminal rows are visible.

---

## Patterns to follow

1. **Clear before typing.** MUI search inputs retain stale values across tests in the same session. Always `Ctrl+A` + `Delete` (or `.fill("")`) before `keyboard.type()`.
2. **Save → wait for progress bar.** After clicking Update Configuration / Proceed / Save, wait `while pb.is_visible(): page.wait_for_timeout(500)` before reading next UI state.
3. **Drive the browser via Playwright MCP for new locators.** Never guess an xpath — open the real DOM, find the element, then encode the locator into [xpath.toml](xpath.toml).
4. **Use markers.** Each new test goes under `@pytest.mark.book_appointment` / `manage_appointment` / `manage_calendar`.
5. **Soft-pass vs hard-fail.** When the env lacks prerequisites (no terminal rows, no slots, etc.), `pytest.skip("[<TC>] reason")` is acceptable — a `print("[soft-pass] ...")` is allowed only when the spec explicitly tolerates the variant.
6. **No false pass / no false fail.** Failure messages must describe what was actually observed. If a test detects a real product bug, the message should include the live repro (date, observed counts, what was expected). See `BUGS_REPORT.md` for examples.

---

## Bug reporting

[BUGS_REPORT.md](BUGS_REPORT.md) tracks the manually-verified product defects detected by the suite. Each entry covers: description, exact reproduction steps, expected vs actual behaviour, evidence reference, impact, and a fix direction.

When a new failure is verified against the live app:
1. Add a section to `BUGS_REPORT.md` with the BUG-NNN id.
2. Link the test case(s) that detect it.
3. Update the test's failure message to reflect the real repro (not a guess).

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `TimeoutError: waiting for locator(...)` on row search | Stale text in search box. Use `Ctrl+A` + `Delete` before `keyboard.type()`. |
| Date filter "From=To=D" returns rows for `D-1` and misses `D` PM rows | Confirmed product bug — see BUG-001 in `BUGS_REPORT.md`. Not a test issue. |
| Employee tab can edit notes on an unassigned row | Confirmed product bug — see BUG-002. |
| `Session expired` mid-suite | SSO cookie expired; delete `employee_cookies.json` (or admin equivalent) and re-run to force fresh login. |
| `Day not bookable — selecting first available date` | The default test office may not have a slot for tomorrow. The booking helper falls back to the first available date; capture the actual booked date from `_complete_booking_flow`'s return dict. |
| Calendar `pb` (progress bar) never settles | Use `while pb.is_visible(): page.wait_for_timeout(500)` rather than `networkidle` — this SPA polls continuously. |

---

## Notes

- Browser profile (`tests/browser_profile/`), employee cookies, screenshots, and local backups are all gitignored.
- Test screenshots from failed runs land under `screenshots/` for inspection but are not part of the regression report.
- The suite is designed to run against the QA environment. Pointing it at staging/production requires updating `[admin].url` and re-validating credentials.
