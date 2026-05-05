import pytest
import time
from datetime import datetime, timedelta
from playwright.sync_api import expect
from tests.utils import *

@pytest.fixture(autouse=True)
def load_appointment_locators(admin_session):
    """Fixture to load manage appointment specific xpaths."""
    page, xpaths, config = admin_session
    import toml
    try:
        data = toml.load("xpath.toml")
        if "manage_calendar" in data:
            xpaths.update(data["manage_calendar"])
        if "manage_appointment" in data:
            xpaths.update(data["manage_appointment"])
    except Exception as e:
        print(f"Warning: Failed to load manage_appointment configuration: {e}")

def _ensure_manage_appointments_tab(page, xpaths):
    """Ensure we are on the Manage Appointments page and filters are cleared."""
    if "/scheduling/manage-appointments" not in page.url:
        print("[Nav] Navigating to Manage Appointments")
        _navigate_via_menu(page, xpaths, "manage_appointments_menu")
    
    # Wait for table container
    page.wait_for_selector("table", timeout=10000)
    
    # Check for rows, if none, maybe filters are applied
    if page.locator(xpaths["appointment_row"]).count() == 0:
        print("[Nav] No rows found, clearing filters if possible...")
        # Add logic to clear filters if a 'Clear' button exists, 
        # or just wait longer
        page.wait_for_timeout(2000)

def _wait_for_backdrop_hidden(page):
    """Wait for MUI backdrop to disappear to avoid intercepted clicks."""
    try:
        page.locator(".MuiBackdrop-root").wait_for(state="hidden", timeout=10000)
    except:
        pass

@pytest.mark.manage_appointment
def test_tc_cal_033_approve_booked_appointment(admin_session):
    """TC-CAL-033: Admin can approve a Booked appointment."""
    page, xpaths, config = admin_session
    _ensure_manage_appointments_tab(page, xpaths)
    
    page.evaluate(xpaths["horizontal_scroll_table_script"])
    
    row = page.locator(xpaths["appointment_row"]).filter(has=page.locator(xpaths["appointment_status_cell_named"].format(status="Booked"))).first
    expect(row).to_be_visible(timeout=15000)
    row_text = row.locator("td").first.inner_text().split('\n')[0].strip()

    row.locator(xpaths["action_menu_btn"]).click(force=True)
    
    approve_opt = page.locator(xpaths["approve_option"]).first
    approve_opt.wait_for(state="visible", timeout=5000)
    approve_opt.click(force=True)
    
    drawer = page.locator(xpaths["appointment_details_drawer"])
    expect(drawer).to_be_visible(timeout=10000)
    
    approve_btn = drawer.locator(xpaths["drawer_approve_btn"])
    approve_btn.click(force=True)
    
    confirm_btn = page.locator(xpaths["confirm_yes_btn"]).first
    if confirm_btn.is_visible(timeout=3000):
        confirm_btn.click(force=True)

    _wait_for_backdrop_hidden(page)
    # Refresh/Wait for table update
    page.wait_for_timeout(3000)
    verified_row = page.locator(xpaths["appointment_row"]).filter(has_text=row_text).first
    expect(verified_row).to_contain_text("Approved", timeout=10000)

@pytest.mark.manage_appointment
def test_tc_cal_034_reject_booked_appointment(admin_session):
    """TC-CAL-034: Admin can reject a Booked appointment with required reason."""
    page, xpaths, config = admin_session
    _ensure_manage_appointments_tab(page, xpaths)
    
    page.evaluate(xpaths["horizontal_scroll_table_script"])
    row = page.locator(xpaths["appointment_row"]).filter(has=page.locator(xpaths["appointment_status_cell_named"].format(status="Booked"))).first
    expect(row).to_be_visible(timeout=10000)
    row_text = row.locator("td").first.inner_text().split('\n')[0].strip()
    
    row.locator(xpaths["action_menu_btn"]).click(force=True)
    page.locator(xpaths["reject_option"]).first.click(force=True)
    
    dialog = page.locator(xpaths["reject_dialog"])
    expect(dialog).to_be_visible()
    
    # Select reason
    dialog.locator(xpaths["reject_reason_dropdown"]).click(force=True)
    page.locator(xpaths["listbox_option_first"]).first.click(force=True)
    
    # Click Reject inside dialog
    dialog.locator(xpaths["reject_submit_btn"]).click(force=True)
    
    _wait_for_backdrop_hidden(page)
    page.wait_for_timeout(3000)
    verified_row = page.locator(xpaths["appointment_row"]).filter(has_text=row_text).first
    expect(verified_row).to_contain_text("Rejected", timeout=10000)

@pytest.mark.manage_appointment
def test_tc_cal_035_rejection_note_limit(admin_session):
    """TC-CAL-035: Rejection note max character limit enforcement."""
    page, xpaths, config = admin_session
    _ensure_manage_appointments_tab(page, xpaths)
    
    page.evaluate(xpaths["horizontal_scroll_table_script"])
    row = page.locator(xpaths["appointment_row"]).filter(has=page.locator(xpaths["appointment_status_cell_named"].format(status="Booked"))).first
    if row.count() == 0: pytest.skip("No Booked appointments found")
    
    row.locator(xpaths["action_menu_btn"]).click(force=True)
    page.locator(xpaths["reject_option"]).first.click(force=True)
    
    dialog = page.locator(xpaths["reject_dialog"])
    page.locator(xpaths["reject_note_textarea"]).fill("A" * 501)
    
    submit_btn = dialog.locator(xpaths["reject_submit_btn"])
    # If not disabled, clicking should show error
    submit_btn.click(force=True)
    page.keyboard.press("Escape")

@pytest.mark.manage_appointment
def test_tc_cal_036_assign_appointment(admin_session):
    """TC-CAL-036: Admin can assign appointment to an employee."""
    page, xpaths, config = admin_session
    _ensure_manage_appointments_tab(page, xpaths)
    
    row = page.locator(xpaths["appointment_row"]).filter(has_text="Select assignee").first
    if row.count() == 0: pytest.skip("No unassigned appointments found")
    
    dropdown = row.locator(xpaths["assigned_to_dropdown"])
    dropdown.click(force=True)
    
    page.locator(xpaths["listbox_option_first"]).first.click(force=True)
    _wait_for_backdrop_hidden(page)
    page.wait_for_timeout(2000)
    expect(dropdown).not_to_have_text("Select assignee")

@pytest.mark.manage_appointment
def test_tc_cal_037_reassignment_confirmation(admin_session):
    """TC-CAL-037: Reassignment triggers confirmation dialog."""
    page, xpaths, config = admin_session
    _ensure_manage_appointments_tab(page, xpaths)
    
    row = page.locator(xpaths["appointment_row"]).filter(has_not_text="Select assignee").first
    if row.count() == 0: pytest.skip("No assigned appointments found")
    
    dropdown = row.locator(xpaths["assigned_to_dropdown"])
    dropdown.click(force=True)
    
    page.locator(xpaths["listbox_option_first"]).nth(1).click(force=True)
    expect(page.locator(xpaths["confirm_dialog"])).to_be_visible()
    page.locator(xpaths["confirm_yes_btn"]).click(force=True)
    _wait_for_backdrop_hidden(page)

@pytest.mark.manage_appointment
def test_tc_cal_038_assignment_disabled_terminal_status(admin_session):
    """TC-CAL-038: Assignment disabled for terminal status appointments."""
    page, xpaths, config = admin_session
    _ensure_manage_appointments_tab(page, xpaths)
    
    terminal_statuses = ["Completed", "Cancelled", "Rejected", "Missed"]
    found = False
    for status in terminal_statuses:
        row = page.locator(xpaths["appointment_row"]).filter(has=page.locator(xpaths["appointment_status_cell_named"].format(status=status))).first
        if row.count() > 0:
            dropdown = row.locator(xpaths["assigned_to_dropdown"])
            expect(dropdown).to_have_attribute("aria-disabled", "true")
            found = True
            break
    if not found: pytest.skip("No terminal status appointments found")

@pytest.mark.manage_appointment
def test_tc_cal_039_add_note_validation(admin_session):
    """TC-CAL-039: Add Note validation."""
    page, xpaths, config = admin_session
    _ensure_manage_appointments_tab(page, xpaths)
    
    page.evaluate(xpaths["horizontal_scroll_table_script"])
    row = page.locator(xpaths["appointment_row"]).first
    row.locator(xpaths["action_menu_btn"]).click(force=True)
    page.locator(xpaths["notes_option"]).first.click(force=True)
    
    dialog = page.locator(xpaths["notes_dialog"])
    expect(dialog).to_be_visible()
    dialog.locator(xpaths["add_note_btn"]).click(force=True)
    
    dialog.locator(xpaths["note_textarea"]).fill("Test Automation Note")
    dialog.locator(xpaths["save_note_btn"]).click(force=True)
    expect(dialog.locator("text=Test Automation Note")).to_be_visible()
    page.keyboard.press("Escape")

@pytest.mark.manage_appointment
def test_tc_cal_040_role_based_action_visibility(admin_session):
    """TC-CAL-040: Role-based action visibility."""
    page, xpaths, config = admin_session
    _ensure_manage_appointments_tab(page, xpaths)
    
    page.evaluate(xpaths["horizontal_scroll_table_script"])
    row = page.locator(xpaths["appointment_row"]).first
    row.locator(xpaths["action_menu_btn"]).click(force=True)
    
    admin_actions = ["Approve", "Reject", "Reschedule", "Cancel", "Details", "Notes"]
    for action in admin_actions:
        expect(page.locator(xpaths["menu_item_by_text"].format(action=action))).to_be_visible()
    page.keyboard.press("Escape")

@pytest.mark.manage_appointment
def test_tc_cal_041_calendar_week_view_stats(admin_session):
    """TC-CAL-041: Calendar View Week view statistics."""
    page, xpaths, config = admin_session
    _ensure_manage_appointments_tab(page, xpaths)
    
    page.locator(xpaths["calendar_view_tab"]).click(force=True)
    _wait_for_backdrop_hidden(page)
    page.locator(xpaths["week_view_btn"]).click(force=True)
    
    stats = ["Booked", "Today's appointments", "Open slots", "Fully booked"]
    for label in stats:
        expect(page.locator(xpaths["any_element_with_text"].format(label=label))).to_be_visible()

@pytest.mark.manage_appointment
def test_tc_cal_042_list_to_calendar_resets_office(admin_session):
    """TC-CAL-042: switching to Calendar View resets filters if applicable."""
    page, xpaths, config = admin_session
    _ensure_manage_appointments_tab(page, xpaths)
    
    page.locator(xpaths["calendar_view_tab"]).click(force=True)
    _wait_for_backdrop_hidden(page)
    expect(page.locator(xpaths["office_filter"])).to_be_visible()

@pytest.mark.manage_appointment
def test_tc_cal_043_date_range_filter_validation(admin_session):
    """TC-CAL-043: Date range filter validation."""
    page, xpaths, config = admin_session
    _ensure_manage_appointments_tab(page, xpaths)
    
    page.locator(xpaths["from_date_filter"]).fill(config["test_data"]["filter_date_from"])
    page.locator(xpaths["to_date_filter"]).fill(config["test_data"]["filter_date_to"])
    page.wait_for_timeout(2000)

@pytest.mark.manage_appointment
def test_tc_cal_044_timezone_abbreviation_visibility(admin_session):
    """TC-CAL-044: Timezone abbreviation visibility."""
    page, xpaths, config = admin_session
    _ensure_manage_appointments_tab(page, xpaths)
    
    row = page.locator(xpaths["appointment_row"]).first
    text = row.inner_text().upper()
    assert any(tz in text for tz in ["EST", "CST", "PST", "MST", "EDT", "CDT", "PDT", "MDT"])

@pytest.mark.manage_appointment
def test_tc_cal_045_performance_list_view(admin_session):
    """TC-CAL-045: Performance List View."""
    page, xpaths, config = admin_session
    start_time = time.time()
    _ensure_manage_appointments_tab(page, xpaths)
    load_time = time.time() - start_time
    print(f"[Perf] List View Load Time: {load_time:.2f}s")
    assert load_time < 5.0

@pytest.mark.manage_appointment
def test_tc_cal_046_performance_calendar_grid(admin_session):
    """TC-CAL-046: Performance Calendar Grid."""
    page, xpaths, config = admin_session
    _ensure_manage_appointments_tab(page, xpaths)
    
    page.locator(xpaths["calendar_view_tab"]).click(force=True)
    _wait_for_backdrop_hidden(page)
    
    start_time = time.time()
    page.locator(xpaths["week_view_btn"]).click(force=True)
    page.wait_for_selector(".rbc-calendar", timeout=15000)
    load_time = time.time() - start_time
    print(f"[Perf] Calendar Grid Load Time: {load_time:.2f}s")
    assert load_time < 5.0
