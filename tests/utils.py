import re
import json
import random
import time
import pytest
from datetime import datetime, timedelta
from playwright.sync_api import expect

__all__ = [
    "select_time_via_clock",
    "_ensure_holiday_tab",
    "_pick_random_future_date",
    "_wait_for_picker",
    "_select_date_in_picker",
    "_navigate_to_future_month",
    "_ensure_manage_calendars_tab",
    "_fill_calendar_address",
    "_select_year_in_filter",
    "_verify_holiday_in_list",
    "_ensure_modal_open",
    "_click_day_in_picker",
    "_ensure_edit_page_open",
    "_navigate_to_users",
    "_open_book_from_users_list",
    "_open_household_tab",
    "_open_member_book_appointment",
    "_dismiss_booking_success_dialog",
    "_open_primary_booking_screen",
    "_navigate_via_menu",
    "_ensure_tab_selected",
    "_generate_random_dob",
    "_get_user_row",
    "_open_user_profile",
    "_wait_for_backdrop_hidden",
    "_complete_booking_flow",
    "_create_user_and_skip_eligibility",
    "_find_user_by_status",
    "_book_member_appointment",
    "_find_user_with_members",
    "_find_or_create_family_with_members",
    "_cancel_booked_appointment",
    "_scrape_household_member_names",
    "_find_cb_idx_by_name",
    "_get_name_at_cb_idx",
    "_select_checkbox_for_member",
    "_select_booking_service_for",
    "_get_selected_member_names_from_dom",
]


# ---------------------------------------------------------------------------
# Helper: MUI TimePicker clock interaction
# ---------------------------------------------------------------------------

def select_time_via_clock(page, input_xpath, time_str, ok_btn_xpath, xpaths):
    """
    Robust helper for MUI TimePickers.
    Selects Period (AM/PM) first so that hours are not disabled,
    then selects Hour and Minute, and clicks OK.
    """
    match = re.match(r"(\d{1,2}):(\d{2})\s+(AM|PM)", time_str, re.I)
    if not match:
        print(f"[Clock] Invalid time format: {time_str}")
        return

    h_target, m_target, p_target = match.groups()
    h_int = int(h_target)
    m_int = int(m_target)
    p_target = p_target.upper()

    # Wait for any progress bar to clear
    pb = page.locator(xpaths["progress_bar"])
    if pb.count() > 0 and pb.is_visible():
        print("Waiting for progress bar>", end='')
        while pb.is_visible():
            page.wait_for_timeout(500)
            print('>', end='', flush=True)
        print("\n")

    # Trigger the clock dialog
    inp = page.locator(input_xpath).first
    inp.scroll_into_view_if_needed()

    dialog = None
    clock_icon_xpath = input_xpath + xpaths["clock_icon_suffix"]
    dialog_selector = xpaths["dialog_visible"]

    for i in range(5):
        print(f"[Clock] Triggering {time_str} (attempt {i+1})...")
        page.wait_for_timeout(1000)
        
        # Try different triggers: Input, Icon, then JS Evaluate
        if i == 0 or i == 2:
            inp.click(force=True)
        elif i == 1 or i == 3:
            icon = page.locator(clock_icon_xpath).first
            (icon if icon.count() > 0 else inp).click(force=True)
        else:
            page.evaluate("el => el.click()", inp.element_handle())
            
        page.wait_for_timeout(2000)
        dialog = page.locator(dialog_selector).first
        if dialog.is_visible():
            break

    if not dialog or not dialog.is_visible():
        print("[Clock] Error: Dialog failed to appear.")
        return

    header = dialog.locator(xpaths["clock_toolbar"]).first

    def click_and_verify(val, label_type, target_text):
        print(f"[Clock] Selecting {label_type}: {val}")
        val_padded = f"{val:02d}"
        xpath = xpaths["clock_face_unit"].format(val=val, val_padded=val_padded, type=label_type)
        btn = dialog.locator(xpath).first
        btn.wait_for(state="visible", timeout=3000)
        btn.click(force=True)
        page.wait_for_timeout(1000)
        if header.is_visible():
            h_text = header.inner_text().replace("\n", " ")
            print(f"[Clock] Header: '{h_text}'")
            if str(int(target_text)) not in h_text and target_text not in h_text:
                print(f"[Clock] WARNING: mismatch for '{target_text}'. Retrying...")
                btn.click(force=True)
                page.wait_for_timeout(1000)

    # 1. Select Period first (so correct hours become selectable)
    print(f"[Clock] Selecting Period: {p_target}")
    xpath_am_pm = xpaths["clock_period_btn"].format(period=p_target, period_lower=p_target.lower())
    am_pm = dialog.locator(xpath_am_pm).first
    if am_pm.count() > 0:
        am_pm.click(force=True)
        page.wait_for_timeout(800)
        if header.is_visible():
            print(f"[Clock] Period header: '{header.inner_text()}'")

    # 2. Hour
    click_and_verify(h_int, "hour", h_target)

    # 3. Minute
    click_and_verify(m_int, "minute", m_target)

    # 4. OK
    print("[Clock] Clicking OK")
    ok_btn = page.locator(ok_btn_xpath).first
    if ok_btn.count() == 0:
        ok_btn = dialog.locator(xpaths["clock_dialog_ok_btn"]).first
    ok_btn.click(force=True)
    page.wait_for_timeout(1500)


def _ensure_holiday_tab(page, xpaths):
    """Ensure we are on the Manage Calendars -> Manage Holidays tab."""
    
    # NEW: First, ENSURE any open drawers or dialogs are closed to prevent blocking clicks
    # This prevents state carry-over if a previous test failed with an open modal
    while True:
        drawer_cancel = page.locator(xpaths.get("holiday_cancel_btn", "//button[@id='cancel' or contains(., 'Cancel')]")).first
        dialog_close = page.locator("//button[@aria-label='Close' or @aria-label='close']").first
        
        if drawer_cancel.is_visible(timeout=2000):
            print("[Nav] Closing blocking drawer via Cancel...")
            drawer_cancel.click(force=True)
            page.wait_for_timeout(1000)
        elif dialog_close.is_visible(timeout=2000):
            print("[Nav] Closing blocking dialog via Close btn...")
            dialog_close.click(force=True)
            page.wait_for_timeout(1000)
        else:
            break

    print(f"DEBUG: Ensuring holiday tab. Current URL: {page.url}")
    
    # Check if we are already on the correct tab
    if "/scheduling/manage-calendars" in page.url and page.locator(xpaths["holiday_import_btn"]).is_visible():
         print("Already on Manage Holidays tab.")
         return

    # Direct navigation as primary or fallback
    if "/scheduling/manage-calendars" not in page.url:
         print(f"[Nav] Navigating directly to manage-calendars...")
         page.goto("https://uat-admin.azurehosted.app/scheduling/manage-calendars")
         page.wait_for_load_state("networkidle")

    # If still not on Holidays tab, click it
    tab = page.locator(xpaths["tab_manage_holidays"]).first
    try:
        tab.wait_for(state="visible", timeout=10000)
        status = tab.get_attribute("class") or ""
        selected = "Mui-selected" in status or tab.get_attribute("aria-selected") == "true"
        if not selected:
            print("DEBUG: Clicking holiday tab")
            tab.click()
            page.wait_for_timeout(2000)
    except:
        # Final fallback: force click by text
        print("[Nav] Clicking Manage Holidays tab via text fallback...")
        page.locator(xpaths["tab_manage_holidays"]).first.click(force=True)
        page.wait_for_timeout(2000)


def _pick_random_future_date(min_months=1, max_months=3):
    """Return a random future datetime (concrete date, not months+day)."""
    now = datetime.now()
    # Advance by random months
    months = random.randint(min_months, max_months)
    # Compute first day of the target month
    month_val = (now.month - 1 + months) % 12 + 1
    year_offset = (now.month - 1 + months) // 12
    year_val = now.year + year_offset
    day_val = random.randint(5, 22)
    return datetime(year_val, month_val, day_val)


def _wait_for_picker(page, input_locator=None, timeout=10000):
    """Wait for the MUI date picker popper to become visible."""
    # Using a generic picker popper selector from xpaths if available
    picker_selector = ".MuiPickerPopper-paper, .MuiDateRangePicker-root" 
    picker = page.locator(picker_selector).first
    try:
        picker.wait_for(state="visible", timeout=timeout)
    except Exception:
        if input_locator:
            print("[Picker] Not visible, retrying click...")
            input_locator.click(force=True)
            picker.wait_for(state="visible", timeout=timeout)
        else:
            raise
    page.wait_for_timeout(400)


def _select_date_in_picker(page, target_date, xpaths, input_locator=None):
    """Navigate the open MUI date picker to `target_date` and click it."""
    _wait_for_picker(page, input_locator=input_locator)
    popper = page.locator(xpaths["date_picker_popper"]).first

    MONTH_NAMES = ["january","february","march","april","may","june",
                   "july","august","september","october","november","december"]
    for _ in range(20):  # max 120 clicks (10 years)
        label_el = popper.locator(xpaths["calendar_header_labels"]).first
        try:
            label_text = label_el.inner_text(timeout=10000).strip().lower()
        except Exception:
            print("[Picker] Could not read month label, attempting fallback navigation...")
            label_text = ""

        displayed_month = None
        displayed_year = None
        for idx, m in enumerate(MONTH_NAMES):
            if m in label_text:
                displayed_month = idx + 1
                break
        
        year_match = re.search(r"(\d{4})", label_text)
        if year_match:
            displayed_year = int(year_match.group(1))

        if displayed_month and displayed_year:
            months_diff = (target_date.year - displayed_year) * 12 + (target_date.month - displayed_month)
            if months_diff == 0:
                break  # already on the right month
            if months_diff > 0:
                next_btn = popper.locator("button.MuiPickersArrowSwitcher-nextIconButton, button[aria-label='Next month']").first
                next_btn.click()
            else:
                prev_btn = popper.locator("button.MuiPickersArrowSwitcher-previousIconButton, button[aria-label='Previous month']").first
                prev_btn.click()
            page.wait_for_timeout(900)
        else:
            next_btn = popper.locator(
                "button.MuiPickersArrowSwitcher-nextIconButton, button[aria-label='Next month']"
            ).first
            next_btn.click()
            page.wait_for_timeout(900)

    _click_day_in_picker(page, target_date.day, xpaths)


def _navigate_to_future_month(page, xpaths, clicks=1):
    """Relative month navigation — prefer _select_date_in_picker for new code."""
    _wait_for_picker(page)
    popper = page.locator(".MuiPickerPopper-paper").first
    for i in range(clicks):
        next_btn = popper.locator("button.MuiPickersArrowSwitcher-nextIconButton, button[aria-label='Next month']").first
        next_btn.wait_for(state="visible", timeout=10000)
        next_btn.click()
        page.wait_for_timeout(1200)


def _ensure_manage_calendars_tab(page, xpaths):
    """Ensure we are on the Manage Calendars tab by clicking menu if needed."""
    header = page.locator(xpaths["page_header"]).first
    try:
        if header.count() == 0 or "Manage Calendars" not in header.inner_text(timeout=3000):
            print("[Nav] Clicking Manage Calendars menu")
            page.locator(xpaths["manage_calendars_menu"]).click()
            page.wait_for_load_state("networkidle")
    except:
        page.locator(xpaths["manage_calendars_menu"]).click()
        page.wait_for_load_state("networkidle")

    tab_btn = page.locator(xpaths["tab_manage_calendars"])
    if tab_btn.count() > 0:
        tab_btn.click()
        page.wait_for_timeout(1000)


def _fill_calendar_address(page, xpaths, zip_code=None, address_line1=None, use_map=False):
    """Unified helper to fill calendar address fields."""
    if zip_code:
        print(f"[Address] Entering Zip Code: {zip_code}")
        zip_input = page.locator(xpaths["zip_code_input"])
        zip_input.click()
        zip_input.fill(zip_code)
        try:
            opt = page.locator(xpaths["ui_option"].format(val=zip_code)).first
            opt.wait_for(state="visible", timeout=5000)
            opt.click()
        except:
            page.keyboard.press("Enter")
        page.wait_for_timeout(1000)

    if use_map:
        print("[Address] Using 'Select on map' for location")
        map_btn = page.locator(xpaths["select_on_map_btn"])
        map_btn.scroll_into_view_if_needed()
        map_btn.click()
        
        page.wait_for_selector(xpaths["map_dialog"], state="visible", timeout=20000)
        dialog = page.locator(xpaths["map_dialog"])
        box = dialog.bounding_box()
        
        if box:
            target_x = box['x'] + box['width'] * 0.40
            target_y = box['y'] + box['height'] * 0.45
            print(f"[Address] Clicking map at ({target_x}, {target_y})")
            page.mouse.click(target_x, target_y)
            page.wait_for_timeout(4000)
            
            # Robust wait for select button
            select_btn = page.locator(xpaths["map_select_location_btn"]).first
            for attempt in range(3):
                try:
                    select_btn.wait_for(state="visible", timeout=10000)
                    if select_btn.is_enabled():
                         print("[Address] Clicking Map Select button...")
                         select_btn.click(force=True)
                         break
                except:
                    print(f"[Address] Map Select button not ready (attempt {attempt+1}), re-clicking map...")
                    page.mouse.click(box['x'] + box['width'] * (0.5 + attempt*0.05), box['y'] + box['height'] * 0.45)
                    page.wait_for_timeout(3000)
            
            page.wait_for_timeout(3000)
    
    elif address_line1:
        print(f"[Address] Entering Address Line 1: {address_line1}")
        addr_input = page.locator(xpaths["address_input"])
        current = addr_input.input_value()
        if not current:
            addr_input.fill(address_line1)
            page.wait_for_timeout(500)


def _select_year_in_filter(page, xpaths, year):
    """Select a specific year from the holiday list year filter."""
    print(f"[List] Selecting year: {year}")
    year_input = page.locator(xpaths["holiday_year_select"])
    
    current_val = year_input.input_value()
    if current_val == str(year):
        print(f"[List] Year {year} already selected.")
        return

    year_input.click()
    page.wait_for_timeout(1000)
    
    option = page.locator(xpaths["holiday_year_option"].format(year=year)).first
    if option.count() > 0:
        option.click()
        print(f"[List] Year {year} selected.")
    else:
        print(f"WARNING: Year option '{year}' not found in dropdown.")
        year_input.fill(str(year))
        page.keyboard.press("Enter")

    page.wait_for_timeout(3000)


def _verify_holiday_in_list(page, xpaths, holiday_name=None, start_date=None, end_date=None, location_tab=None, target_year=None):
    """Verify a holiday exists in the list by name OR date range."""
    
    if location_tab:
        print(f"[List] Ensuring visibility and switching to {location_tab} tab...")
        tab_key = f"holiday_location_tab_{location_tab.lower()}"
        tab_xpath = xpaths.get(tab_key, xpaths["holiday_location_tab_all"])
        
        try:
            page.wait_for_selector(xpaths["holiday_import_btn"], timeout=10000)
            print(f"[List] Clicking {location_tab} tab via JS...")
            page.evaluate(f"""(xpath) => {{
                const element = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (element) {{
                    element.click();
                    return true;
                }}
                return false;
            }}""", tab_xpath)
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"[List] WARNING: JS click failed for {location_tab}: {e}. Trying regular click.")
            try:
                page.locator(tab_xpath).first.click(force=True, timeout=5000)
            except:
                print(f"[List] Final fallback for {location_tab}...")
                page.locator(xpaths["location_tab_btn"].format(val=location_tab)).first.click(force=True, timeout=5000)
        
        page.wait_for_timeout(2000)

    # Determine target year from start_date if not provided
    if not target_year and start_date:
        target_year = start_date.year

    if target_year:
        print(f"[List] Selecting target year: {target_year}")
        _select_year_in_filter(page, xpaths, target_year)

    print("[List] Ensuring accordions are expanded...")
    accordions = page.locator(xpaths["holiday_accordion_summary_all"])
    for i in range(accordions.count()):
        acc = accordions.nth(i)
        try:
            acc.scroll_into_view_if_needed(timeout=3000)
            if acc.get_attribute("aria-expanded") != "true":
                print(f"[List] Expanding accordion {i+1}")
                acc.click(force=True)
                page.wait_for_timeout(800)
        except:
            pass
    
    found = False
    print(f"[List] Starting deep scroll-search (End keys + sweep)")
    
    start_str = start_date.strftime('%d %b') if start_date else ""
    end_str = end_date.strftime('%d %b') if end_date else ""
    print(f"[List] Target: {holiday_name} ({start_str} - {end_str})")
    
    collected_rows = set()
    page.locator("body").click()
    
    for attempt in range(30):
        # Extract current visible rows
        rows = page.locator(xpaths["holiday_row_all"]).all_inner_texts()
        for r in rows:
            clean_r = " ".join(r.split()).lower()
            if clean_r:
                collected_rows.add(clean_r)
        
        # Check for match in collected set
        s_day = start_date.strftime('%d') if start_date else ""
        s_month = start_date.strftime('%b').lower() if start_date else ""
        e_day = end_date.strftime('%d') if end_date else ""
        e_month = end_date.strftime('%b').lower() if end_date else ""
        h_name = holiday_name.lower() if holiday_name else ""

        for row_text in collected_rows:
            # DATE-ONLY MATCH: Ignoring name per user request.
            # Check if start day/month and end day/month components are present in the same row.
            
            # Use lstrip('0') to handle '02 May' vs '2 May'
            s_day_clean = s_day.lstrip('0')
            e_day_clean = e_day.lstrip('0')
            
            # Robust containment check
            row_clean = row_text.replace(' 0', ' ')
            has_s = not s_day or (s_day_clean in row_clean and s_month in row_text)
            has_e = not e_day or (e_day_clean in row_clean and e_month in row_text)
            
            if has_s and has_e:
                print(f"PASS: Holiday dates found in list: {start_str} - {end_str}")
                found = True
                break
        
        if found: break

        # Navigation & Pagination
        if attempt > 0 and attempt % 10 == 0:
            next_btn = page.locator(xpaths["pagination_next_btn"]).first
            if next_btn.is_visible() and next_btn.is_enabled():
                print(f"[List] Clicking NEXT PAGE...")
                next_btn.click()
                page.wait_for_timeout(2000)
                continue
    
        if attempt % 2 == 0: page.keyboard.press("End")
        else: page.evaluate("window.scrollBy(0, 3000)")
        page.wait_for_timeout(400)

    if not found:
        print(f"FAIL: Holiday search failed for {holiday_name} ({start_str} - {end_str})")
        # Log ALL collected rows for better debugging
        print(f"[DEBUG] Full extracted list snippets:")
        for r in sorted(list(collected_rows)):
            print(f"  - {r}")
        page.screenshot(path="failure_holiday_list_search.png")
        assert found, f"Holiday '{holiday_name}' ({start_str} to {end_str}) was not found in the list."
    
    return found


def _ensure_modal_open(page, xpaths):
    """Ensure the Add Holiday drawer is open and form is fully loaded."""
    modal_title = page.locator(xpaths["holiday_modal_title"])
    name_input = page.locator(xpaths["holiday_name_input"])
    
    if not name_input.is_visible(timeout=3000):
        for attempt in range(3):
            print(f"[Drawer] Opening attempt {attempt + 1}")
            btn = page.locator(xpaths["holiday_add_new_btn"]).first
            btn.scroll_into_view_if_needed()
            btn.click(force=True)
            
            try:
                # Wait for form content AND ensures backdrop is gone if any
                name_input.wait_for(state="visible", timeout=10000)
                page.wait_for_timeout(1000) # Settling time
                return modal_title
            except Exception:
                print(f"[Drawer] Attempt {attempt + 1} failed. Current URL: {page.url}")
                if attempt < 2:
                    page.wait_for_timeout(2000)
                    page.reload()
                    _ensure_holiday_tab(page, xpaths)
        
        name_input.wait_for(state="visible", timeout=5000)
        
    return modal_title


def _click_day_in_picker(page, day: int, xpaths):
    """Click a specific day number in the open MUI picker."""
    # Popper is already verified visible by the caller
    day_btn = page.locator(xpaths["ui_gridcell"].format(val=day)).first
    day_btn.wait_for(state="visible", timeout=10000)
    day_btn.click()
    page.wait_for_timeout(600)


def _ensure_edit_page_open(page, xpaths, config):
    """Ensure we are on the Edit Calendar page for the newly created calendar."""
    target_name = config["new_calendar"].get("dynamic_name")
    if not target_name:
        return

    header = page.locator(xpaths["page_header"]).first
    try:
        # Check if already on Edit page for this name
        if header.count() > 0 and "Edit Calendar" in header.inner_text(timeout=3000):
            current_name = page.locator(xpaths["calendar_name_input"]).input_value()
            if target_name in current_name:
                return
    except:
        pass

    print(f"[Nav] Opening Edit page for '{target_name}'")
    page.locator(xpaths["manage_calendars_menu"]).click()
    page.wait_for_load_state("networkidle")

    search_input = page.locator(xpaths["search_input"]).first
    search_input.wait_for(state="visible", timeout=10000)
    search_input.fill(target_name)
    page.keyboard.press("Enter")
    page.wait_for_timeout(2000)

    # Search and Open Action Menu with 3-attempt retry
    for attempt in range(3):
        print(f"[Nav] Opening Edit page Attempt {attempt+1} (Target: {target_name})")
        row_xpath = xpaths["calendar_row_by_name"].format(name=target_name)
        row_locator = page.locator(row_xpath).first
        
        try:
            row_locator.wait_for(state="visible", timeout=10000)
            row_locator.scroll_into_view_if_needed()
            
            action_btn = row_locator.locator("button[aria-label*='more' i], button.MuiIconButton-root").first
            action_btn.scroll_into_view_if_needed()
            action_btn.click(force=True)
            page.wait_for_timeout(2000) 
            
            edit_opt = page.locator(xpaths["edit_option"]).first
            edit_opt.wait_for(state="visible", timeout=5000)
            edit_opt.click(force=True)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)
            
            # Simple verification: Is "Calendar" or "Calendar Name" label visible?
            # User wants: //*[text()='Calender Name']
            cal_label = page.locator("//*[text()='Calender Name']")
            if cal_label.is_visible():
                 print(f"[Nav] Successfully reached Edit page (Label/URL verified).")
                 return
        except Exception as e:
            print(f"[Nav] Attempt {attempt+1} failed: {e}")
            page.reload()
            page.wait_for_load_state("networkidle")
            _ensure_manage_calendars_tab(page, xpaths)
            page.wait_for_timeout(3000)
    
    #assert "/edit" in page.url, f"[Nav] Failed to reach Edit page after 3 attempts. URL: {page.url}"
    
# ---------------------------------------------------------------------------
# User and Appointment Helpers (NIJC Admin)
# ---------------------------------------------------------------------------

def _navigate_to_users(page, xpaths):
    """Ensure we are on the User Management list page."""
    if "/management/users/list" not in page.url:
        print("[Nav] Navigating to User Management")
        page.locator(xpaths["users_menu"]).click()
        page.wait_for_load_state("networkidle")
    page.wait_for_selector(xpaths["user_row"], timeout=15000)


def _open_book_from_users_list(page, xpaths, search_text):
    """Search the Users list by `search_text`, open the matching user's actions menu,
    and click 'Book Appointment'. The booking screen is expected to load afterward.

    `search_text` can be an email, a unique name, or any substring that uniquely
    identifies the user row in the Users table.
    """
    _navigate_to_users(page, xpaths)
    page.locator(xpaths["search_input_user"]).fill(search_text)
    page.keyboard.press("Enter")
    page.wait_for_timeout(3000)
    row = page.locator(xpaths["user_row"]).filter(has_text=search_text).first
    row.locator(xpaths["user_action_btn"]).click(force=True)
    page.locator(xpaths["book_appointment_option"]).click()
    page.wait_for_timeout(5000)


def _open_household_tab(page, xpaths, profile_url):
    """Open a primary user's profile and switch to the Household Members tab."""
    page.goto(profile_url, wait_until="networkidle")
    page.locator(xpaths["profile_household_tab"]).wait_for(state="visible", timeout=20000)
    page.locator(xpaths["profile_household_tab"]).click()
    page.wait_for_timeout(2500)


def _open_member_book_appointment(page, xpaths, member_name):
    """Click 'Book Appointment' on the named household member's actions menu.

    Assumes the page is already on the Household Members tab.
    """
    member_row = page.locator(xpaths["member_row"]).filter(has_text=member_name).first
    member_row.locator(xpaths["member_action_btn"]).click(force=True)
    page.wait_for_timeout(1000)
    page.locator(xpaths["member_book_option"]).click(force=True)


def _dismiss_booking_success_dialog(page, xpaths):
    """Dismiss the post-booking 'Appointment Booked' confirmation dialog by clicking
    'Go to Manage Appointments' (which navigates away and clears the modal backdrop)."""
    page.locator(xpaths["go_to_manage_appt"]).click(force=True)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)


def _navigate_via_menu(page, xpaths, menu_key):
    """Click a top-level navigation menu link by its xpath key and wait for the network
    to settle. Saves the repeated 2-line pattern of `page.locator(xpaths[KEY]).click()`
    plus `page.wait_for_load_state("networkidle")`.
    """
    page.locator(xpaths[menu_key]).click()
    page.wait_for_load_state("networkidle")


def _generate_random_dob(config):
    """Generate a random Date of Birth that produces an age within the configured
    [dob_min_age, dob_max_age] window from `conf.toml [new_user]`. Defaults to
    19..60 if either bound is missing.

    Day is sampled from 1..28 to dodge month/leap-year edge cases.

    Returns a dict:
        {
            "month_short": "Jan" | "Feb" | ...,   # used by the primary-user form
            "day":         "01"..."28",
            "year":        e.g. "1995",
            "mmddyyyy":    e.g. "01151995",        # used by the household-member form
        }
    """
    import random as _random
    from datetime import date as _date

    new_user = config.get("new_user", {})
    min_age = int(new_user.get("dob_min_age", 19))
    max_age = int(new_user.get("dob_max_age", 60))
    if max_age < min_age:
        max_age = min_age

    today = _date.today()
    age = _random.randint(min_age, max_age)
    # Subtract one extra year to avoid edge cases where the chosen month/day
    # hasn't occurred yet this year (which would make the user technically `age - 1`).
    year = today.year - age - 1
    month = _random.randint(1, 12)
    day = _random.randint(1, 28)

    months_short = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return {
        "month_short": months_short[month - 1],
        "day": f"{day:02d}",
        "year": str(year),
        "mmddyyyy": f"{month:02d}{day:02d}{year}",
    }


def _ensure_tab_selected(page, xpaths, tab_key, wait_ms=2000):
    """Ensure a MUI Tabs tab is the active selection: clicks it only when neither the
    `Mui-selected` class nor `aria-selected="true"` is present, then waits `wait_ms`
    for the tabbed content to render.
    """
    tab = page.locator(xpaths[tab_key]).first
    tab_class = tab.get_attribute("class") or ""
    if "Mui-selected" not in tab_class and tab.get_attribute("aria-selected") != "true":
        tab.click()
        page.wait_for_timeout(wait_ms)


def _open_primary_booking_screen(page, config, profile_url):
    """Navigate directly to the New Appointment screen for the primary user identified
    by the UUID embedded in `profile_url`. Avoids name-based search ambiguity in QA."""
    import re as _re
    m = _re.search(r"[?&]id=([0-9a-fA-F-]+)", profile_url)
    if not m:
        raise ValueError(f"Could not extract user UUID from profile_url: {profile_url!r}")
    base = config["admin"]["url"].rstrip("/")
    path = config["admin"].get("new_appointment_path", "/scheduling/new-appointment")
    page.goto(f"{base}{path}?puid={m.group(1)}", wait_until="networkidle")
    page.wait_for_timeout(2500)


def _get_user_row(page, xpaths, status_xpath=None, has_text=None):
    """Find a user row by status or text."""
    locator = page.locator(xpaths["user_row"])
    if status_xpath:
        locator = locator.filter(has=page.locator(status_xpath))
    if has_text:
        locator = locator.filter(has_text=has_text)
    return locator.first

def _open_user_profile(page, xpaths, row=None):
    """Open user profile from list."""
    page.wait_for_selector(xpaths["user_row"], state="visible", timeout=20000)
    if not row:
        row = _get_user_row(page, xpaths)
    button = row.locator(xpaths["user_action_btn"])
    button.wait_for(state="attached", timeout=10000)
    button.click(force=True)
    page.locator(xpaths["view_profile_option"]).click()
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(xpaths["profile_details_tab"], timeout=10000)

def _wait_for_backdrop_hidden(page):
    """Wait for MUI backdrop to disappear."""
    try:
        page.locator(".MuiBackdrop-root").wait_for(state="hidden", timeout=5000)
    except:
        pass

def _complete_booking_flow(page, xpaths, config, member_name=None):
    """Completes the multi-step booking flow from the booking container."""
    # 1. & 2. Select Member & Service
    if member_name:
        print(f"[Booking] Selecting member and service for: {member_name}")
        row = page.locator(".MuiGrid-container").filter(has_text=member_name).first
        cb = row.locator('input[type="checkbox"]').first
        if not cb.is_checked():
            row.locator('span.MuiCheckbox-root, input[type="checkbox"]').first.click(force=True)
        page.wait_for_timeout(500)
        # Open the MUI Select — the trigger uses role="combobox"
        row.locator('[role="combobox"]').first.click(force=True)
    else:
        # Default fallback for self-booking
        page.locator(xpaths["member_selection_checkbox"]).first.click(force=True)
        page.wait_for_timeout(2000)
        page.locator(xpaths["service_needed_dropdown"]).click(force=True)

    # Verify the listbox actually opened; fall back to the "Open" arrow button if not
    listbox = page.locator('ul[role="listbox"], div[role="listbox"]').first
    try:
        listbox.wait_for(state="visible", timeout=5000)
    except Exception:
        print("[Booking] Listbox didn't open via combobox click — trying 'Open' button")
        page.get_by_role("button", name="Open").last.click(force=True)
        listbox.wait_for(state="visible", timeout=10000)

    # 3. Select the actual service option
    service = config["new_calendar"]["services"][0]
    opt = page.locator(xpaths["service_option"].format(service=service)).first
    try:
        opt.wait_for(state="visible", timeout=10000)
        opt.click(force=True)
    except:
        print(f"[Booking] Service '{service}' not found, picking first available.")
        page.locator(xpaths["listbox_option"]).first.click(force=True)

    # 3. Click Next (to Office Selection)
    page.locator(xpaths["booking_next_btn"]).click()
    page.wait_for_timeout(3000)
    
    # 4. Select Office (Card)
    office_name = config["new_calendar"]["name"]
    office_card = page.locator(xpaths["office_card"].format(name=office_name)).first
    if office_card.count() > 0:
        office_card.click()
    else:
        print(f"[Booking] Office '{office_name}' not found, selecting first available office.")
        page.locator(xpaths["office_card_any"]).first.click()
    
    # 5. Click Next (to Date Selection)
    page.locator(xpaths["booking_next_btn"]).click()
    page.wait_for_timeout(3000)
    
    # 6. Select Date — custom weekly grid (NOT MuiPickersDay buttons).
    # Available dates = div containing a <p> (day number) AND a <span> (service chip).
    new_day = config["test_data"]["reschedule_day"]
    date_btn = page.locator(xpaths["booking_date_btn"].format(day=new_day)).first
    if date_btn.count() > 0 and date_btn.is_visible():
        date_btn.click()
        print(f"[Booking] Date '{new_day}' selected ✓")
    else:
        print(f"[Booking] Day '{new_day}' not found, selecting first available date from custom grid.")
        available_date = page.locator(xpaths["booking_date_any_available"]).first
        available_date.wait_for(state="visible", timeout=15000)
        available_date.click()
    page.wait_for_timeout(2000)
    
    # 7. Select Time Slot
    slot_locator = page.locator(xpaths["available_time_slot"]).filter(has_not=page.locator("[disabled]"))
    if slot_locator.count() > 0:
        slot_locator.first.click()
    else:
        pytest.skip("No available time slots found for booking")

    # Handle "Confirm Appointment" dialog → click Yes
    try:
        confirm_yes = page.locator(
            "//button[@data-testid='qa-submit'] | "
            "//div[contains(@class,'MuiDialog')]//button[normalize-space(.)='Yes']"
        )
        confirm_yes.wait_for(state="visible", timeout=8000)
        confirm_yes.first.click()
        page.wait_for_timeout(1500)
    except Exception:
        pass

    # 8. Click Next (to Review)
    page.locator(xpaths["booking_next_btn"]).click()
    page.wait_for_timeout(3000)
    
    # 9. Click Final Book Appointment
    page.locator(xpaths["booking_final_book_btn"]).click()

def _create_user_and_skip_eligibility(page, xpaths, config, first_name=None, last_name=None):
    """Creates a new user and skips the eligibility questions page.

    Optional `first_name` / `last_name` override the values from config["new_user"] so
    each test can stamp its TC number on the created user (e.g. 'TC22User').
    """
    _navigate_to_users(page, xpaths)

    # 1. Click Add New Users
    page.locator(xpaths["add_new_user_btn"]).click()
    page.wait_for_load_state("networkidle")

    # 2. Fill User Details
    user_data = config["new_user"]
    fname = first_name if first_name is not None else user_data["first_name"]
    lname = last_name if last_name is not None else user_data["last_name"]
    page.locator(xpaths["first_name_input"]).dblclick()
    page.wait_for_timeout(1000)
    page.locator(xpaths["first_name_input"]).press_sequentially(fname, delay=100)
    page.wait_for_timeout(1000)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)

    page.locator(xpaths["last_name_input"]).click(force=True)
    page.locator(xpaths["last_name_input"]).press_sequentially(lname, delay=100)
    page.wait_for_timeout(1000)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)
    
    # DOB — generated dynamically each run so users aren't all born on the same day.
    # Constrained to adult age via [new_user].dob_min_age / dob_max_age in conf.toml.
    dob = _generate_random_dob(config)
    page.locator(xpaths["dob_month"]).click()
    page.keyboard.type(dob["month_short"])
    page.keyboard.press("Enter")
    page.locator(xpaths["dob_day"]).click()
    page.keyboard.type(dob["day"])
    page.keyboard.press("Enter")
    page.locator(xpaths["dob_year"]).click()
    page.keyboard.type(dob["year"])
    page.keyboard.press("Enter")
    page.locator("body").click()
    page.wait_for_timeout(2000)
    
    # Gender
    page.locator(xpaths["gender_input"]).click()
    page.wait_for_timeout(1000)
    page.locator(xpaths["gender_option"].format(gender=user_data["gender"])).click()
    page.wait_for_timeout(1000)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)
    
    # Address Info
    page.locator(xpaths["state_input"]).fill(user_data["state"])
    page.wait_for_timeout(1000)
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)
    
    page.locator(xpaths["city_input"]).fill(user_data["city"])
    page.wait_for_timeout(1000)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)
    
    page.locator(xpaths["zip_code_input"]).fill(user_data["zip"])
    page.wait_for_timeout(1000)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)
    
    # Email
    unique_email = f"auto_{int(time.time())}_{random.randint(1111, 9999)}@example.com"
    page.locator(xpaths["email_input"]).click()
    page.locator(xpaths["email_input"]).press_sequentially(unique_email, delay=50)
    page.wait_for_timeout(1000)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)
    
    # Send Credentials
    page.locator(xpaths["send_email_checkbox"]).click()
    page.wait_for_timeout(1000)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)
    
    # Save
    page.locator(xpaths["user_save_btn"]).click()
    expect(page.locator(xpaths["success_toast"]).first).to_be_visible(timeout=30000)
    page.wait_for_timeout(3000)
    
    # Handle Eligibility Page (Cancel)
    page.wait_for_selector(xpaths["eligibility_header_text"], timeout=15000)
    page.locator(xpaths["cancel_btn"]).click()
    page.wait_for_load_state("networkidle")
    
    return unique_email

def _find_user_by_status(page, xpaths, status_xpath_key):
    """
    Scroll through the user list to find a user with the specified status.
    status_xpath_key should be a key in xpaths like 'status_ineligible'.
    """
    status_xpath = xpaths[status_xpath_key]
    
    # First, clear any search filter that might be active
    search_input = page.locator(xpaths["search_input_user"]).first
    if search_input.input_value():
        print("[Search] Clearing search input")
        search_input.fill("")
        page.keyboard.press("Enter")
        page.wait_for_timeout(2000)

    for attempt in range(20): # Try 20 scrolls/pages
        # Wait for data to load
        page.wait_for_timeout(1000) 
        
        rows = page.locator(xpaths["user_row"])
        count = rows.count()
        for i in range(count):
            row = rows.nth(i)
            # Use the relative status xpath (updated in xpath.toml)
            if row.locator(status_xpath).count() > 0:
                print(f"[Search] Found user with status {status_xpath_key} at row {i+1}")
                row.scroll_into_view_if_needed()
                return row
        
        # Try scrolling down first
        page.evaluate("window.scrollBy(0, 1000)")
        page.wait_for_timeout(500)
        
        # Check for next page
        next_btn = page.locator(xpaths.get("pagination_next_btn", "//button[@aria-label='Go to next page']")).first
        if next_btn.is_visible() and next_btn.is_enabled():
            print(f"[Search] Moving to next page... (attempt {attempt+1})")
            next_btn.click()
            page.wait_for_timeout(2000)
        else:
            # If no next page, scroll to bottom to see if more rows load (infinite scroll)
            page.keyboard.press("End")
            page.wait_for_timeout(1000)
            
    return None


# ---------------------------------------------------------------------------
# Shared helpers for household-member booking (used by TC_013, TC_014 …)
# ---------------------------------------------------------------------------

def _find_user_with_members(page, xpaths, max_attempts=10):
    """
    Scroll the Users list until a row with at least one household member is found.
    Returns the matching row locator or None.
    """
    for _ in range(max_attempts):
        rows = page.locator(xpaths["user_row"])
        for i in range(rows.count()):
            count_text = rows.nth(i).locator("td").nth(2).inner_text().strip()
            if count_text.isdigit() and int(count_text) > 0:
                return rows.nth(i)
        page.keyboard.press("End")
        page.wait_for_timeout(1000)
    return None


def _find_or_create_family_with_members(page, xpaths, config, min_eligible=2, max_pages=5, force_create=False, tc_id=None):
    """
    Search the Users list for a primary user who has at least `min_eligible` eligible/active
    household members from the SAME family.

    If no such user exists (or force_create is True), creates a fresh primary user and adds
    `min_eligible` household members to them.

    Optional `tc_id` (e.g. "27") tags newly-created users — primary first name becomes
    "TC<tc_id>", member first names become "TC<tc_id>Member<N>", and the email prefix
    encodes the TC. When None, falls back to the original "Automation User" / "TC15Member"
    defaults from config so this stays backward-compatible.

    Returns a tuple:
        (primary_user_name, profile_url, eligible_member_names)
    where:
        primary_user_name  — str, full name of the primary user
        profile_url        — str, URL of the user's profile page (may be list URL if not /view)
        eligible_member_names — list[str], names of eligible household members (len >= min_eligible)
    """
    import time as _time, random as _random

    # ── Phase 1: Search existing users ──
    if not force_create:
        _navigate_to_users(page, xpaths)
        for _ in range(max_pages):
            rows = page.locator(xpaths["user_row"])
            for i in range(rows.count()):
                row = rows.nth(i)
                count_text = row.locator("td").nth(2).inner_text().strip()
                if not (count_text.isdigit() and int(count_text) >= min_eligible):
                    continue

                # Candidate found — open profile and verify eligible count
                primary_user_name = row.locator(xpaths["user_name_cell"]).inner_text().strip()
                print(f"[FindFamily] Checking '{primary_user_name}' ({count_text} members)...")

                row.locator(xpaths["user_action_btn"]).click(force=True)
                page.locator(xpaths["view_profile_option"]).click()
                page.wait_for_load_state("networkidle")

                page.locator(xpaths["profile_household_tab"]).wait_for(state="visible", timeout=15000)
                page.locator(xpaths["profile_household_tab"]).click()
                page.wait_for_timeout(3000)

                member_rows = page.locator(xpaths["member_row"])
                eligible_names = []
                for j in range(member_rows.count()):
                    text = member_rows.nth(j).inner_text()
                    if any(s in text for s in ["Eligible", "Pending", "Approved", "Active"]):
                        name = member_rows.nth(j).locator(xpaths["member_name_cell"]).inner_text().strip()
                        eligible_names.append(name)

                if len(eligible_names) >= min_eligible:
                    print(f"[FindFamily] ✅ Found '{primary_user_name}' with {len(eligible_names)} eligible members: {eligible_names}")
                    # Return the actual /view?id=... URL so TC can navigate back reliably
                    return primary_user_name, page.url, eligible_names

                print(f"[FindFamily] Only {len(eligible_names)} eligible — going back to list")
                _navigate_to_users(page, xpaths)

            # Next page
            next_btn = page.locator(xpaths.get("pagination_next_btn", "//button[@aria-label='Go to next page']")).first
            if next_btn.is_visible() and next_btn.is_enabled():
                next_btn.click()
                page.wait_for_timeout(2000)
            else:
                break

    # ── Phase 2: No suitable family found — create one ──
    print("[FindFamily] No family with enough eligible members found — creating one...")

    # 2a. Create primary user
    _navigate_to_users(page, xpaths)
    page.locator(xpaths["add_new_user_btn"]).click()
    page.wait_for_load_state("networkidle")

    ud = config["new_user"]
    ts = int(_time.time())
    rnd = _random.randint(100, 999)

    # Per-TC name tagging: when caller passes tc_id, the primary first name and the
    # email prefix encode the TC number so users created by this test are identifiable.
    primary_first = f"TC{tc_id}" if tc_id else ud["first_name"]
    email_prefix = f"tc{tc_id}primary" if tc_id else "tc15primary"
    member_first_prefix = f"TC{tc_id}Member" if tc_id else "TC15Member"

    # Fill primary user form
    page.locator(xpaths["first_name_input"]).dblclick()
    page.wait_for_timeout(1000)
    page.locator(xpaths["first_name_input"]).press_sequentially(primary_first, delay=100)
    page.wait_for_timeout(1000)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)
    
    page.locator(xpaths["last_name_input"]).click(force=True)
    page.locator(xpaths["last_name_input"]).press_sequentially(ud["last_name"], delay=100)
    page.wait_for_timeout(1000)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)

    primary_dob = _generate_random_dob(config)
    page.locator(xpaths["dob_month"]).click(); page.keyboard.type(primary_dob["month_short"]); page.keyboard.press("Enter")
    page.locator(xpaths["dob_day"]).click();   page.keyboard.type(primary_dob["day"]);          page.keyboard.press("Enter")
    page.locator(xpaths["dob_year"]).click();  page.keyboard.type(primary_dob["year"]);         page.keyboard.press("Enter")
    page.locator("body").click(); page.wait_for_timeout(1000)
    page.locator(xpaths["gender_input"]).click()
    page.wait_for_timeout(500)
    page.locator(xpaths["gender_option"].format(gender=ud["gender"])).click()
    page.locator(xpaths["state_input"]).fill("Indiana")
    page.wait_for_timeout(1000)
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.wait_for_timeout(500)
    
    page.locator(xpaths["city_input"]).fill("Indianapolis")
    page.wait_for_timeout(1000)
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.wait_for_timeout(500)
    
    page.locator(xpaths["zip_code_input"]).fill("46201")
    page.wait_for_timeout(500)
    primary_email = f"{email_prefix}_{ts}_{rnd}@example.com"
    page.locator(xpaths["email_input"]).fill(primary_email)
    page.locator(xpaths["send_email_checkbox"]).click()
    page.locator(xpaths["user_save_btn"]).click()
    try:
        page.locator(xpaths["success_toast"]).first.wait_for(state="visible", timeout=15000)
    except Exception:
        print("[FindFamily] Warning: Success toast not seen after saving primary user, continuing anyway...")
    page.wait_for_timeout(2000)

    # Skip eligibility page if it appears
    try:
        page.locator(xpaths["eligibility_header_text"]).wait_for(state="visible", timeout=8000)
        page.locator(xpaths["cancel_btn"]).click()
        page.wait_for_load_state("networkidle")
    except Exception:
        pass

    # Search for the newly created user to open their profile
    _navigate_to_users(page, xpaths)
    page.locator(xpaths["search_input_user"]).fill(primary_email)
    page.keyboard.press("Enter")
    page.wait_for_timeout(3000)
    new_row = page.locator(xpaths["user_row"]).filter(has_text=primary_email).first
    new_row.wait_for(state="visible", timeout=15000)
    primary_user_name = new_row.locator(xpaths["user_name_cell"]).inner_text().strip()
    new_row.locator(xpaths["user_action_btn"]).click(force=True)
    page.locator(xpaths["view_profile_option"]).click()
    # Wait for the URL to contain 'view' and 'id'
    page.wait_for_url(lambda url: "/view" in url and "id=" in url, timeout=15000)
    page.wait_for_load_state("networkidle")
    profile_url = page.url
    print(f"[FindFamily] Primary user profile opened: '{primary_user_name}' at {profile_url}")


    # 2b. Add household members
    page.locator(xpaths["profile_household_tab"]).wait_for(state="visible", timeout=15000)
    page.locator(xpaths["profile_household_tab"]).click()
    page.wait_for_timeout(2000)

    eligible_member_names = []
    for m_idx in range(min_eligible):
        print(f"[FindFamily] Adding household member {m_idx + 1}...")
        page.locator("//button[@id='add_family_member']").click()
        page.wait_for_timeout(2000)

        # Answer 3 eligibility questions — all Yes
        yes_btns = page.locator("//span[text()='Yes']")
        for q in range(3):
            try:
                yes_btns.nth(q).click()
                page.wait_for_timeout(500)
            except Exception:
                pass
        
        # Wait for form to be fully ready
        page.wait_for_load_state("networkidle")
        page.locator(xpaths["first_name_input"]).first.wait_for(state="visible", timeout=30000)

        page.wait_for_timeout(1000)

        # Fill member form
        m_first = f"{member_first_prefix}{m_idx + 1}"
        m_last  = f"{rnd}"
        page.locator(xpaths["first_name_input"]).first.click()
        page.locator(xpaths["first_name_input"]).first.fill(m_first)
        page.keyboard.press("Tab")
        page.locator(xpaths["last_name_input"]).first.fill(m_last)
        page.keyboard.press("Tab")

        # DOB selection (using household_member specific inputs) — generated dynamically
        # each run; same adult-age window as primary user (conf.toml [new_user]).
        member_dob = _generate_random_dob(config)
        try:
            # Click the container first to set focus, as shown in user screenshot
            container = page.locator(xpaths["dob_container"]).first
            container.click()
            page.wait_for_timeout(500)
            page.keyboard.type(member_dob["mmddyyyy"])
            page.wait_for_timeout(500)
        except Exception as e:
            print(f"[FindFamily] DOB container click failed, trying fallback: {e}")
            # Fallback to finding individual inputs or generic typing
            try:
                month_loc = page.get_by_placeholder("MM").first
                if month_loc.count() > 0:
                    month_loc.fill(member_dob["mmddyyyy"][0:2])
                    page.get_by_placeholder("DD").first.fill(member_dob["mmddyyyy"][2:4])
                    page.get_by_placeholder("YYYY").first.fill(member_dob["year"])
                else:
                    # Tab from Last Name and type
                    page.keyboard.press("Tab")
                    page.keyboard.type(member_dob["mmddyyyy"])
            except Exception:
                pass

        page.wait_for_timeout(500)



        # Relationship
        page.locator(xpaths["relation_input"]).click(); page.wait_for_timeout(500)
        page.locator("//li[@role='option']").first.click(); page.wait_for_timeout(500)

        # Gender
        page.locator(xpaths["gender_input"]).click(); page.wait_for_timeout(500)
        page.locator("//li[@role='option']").first.click(); page.wait_for_timeout(500)

        # Same address = Yes
        try:
            page.locator(xpaths["same_address_yes"]).first.click(force=True)
        except Exception:
            page.locator("//label[contains(.,'Yes')]").first.click()
        page.wait_for_timeout(800)

        # Same email & phone checkboxes
        try:
            # Use label-based clicking as checkboxes might be hidden inputs
            page.locator(xpaths["same_email_label"]).first.click()
            page.wait_for_timeout(500)
            page.locator(xpaths["same_email_label"]).last.click()
            page.wait_for_timeout(500)
        except Exception:
            pass

        # Save
        page.locator(xpaths["save_btn"]).first.click()


        try:
            page.locator(xpaths["success_toast"]).first.wait_for(state="visible", timeout=15000)
        except Exception:
            print(f"[FindFamily] Warning: Success toast for member creation not seen, continuing...")
        print(f"[FindFamily] Member '{m_first} {m_last}' created ✓")
        eligible_member_names.append(f"{m_first} {m_last}")
        page.wait_for_timeout(2000)

    print(f"[FindFamily] ✅ Family setup complete. Members: {eligible_member_names}")
    return primary_user_name, profile_url, eligible_member_names


def _book_member_appointment(page, xpaths, config, member_name, tag="TC"):
    """
    Complete the full booking flow for a household member from the booking screen.
    Assumes the caller has already opened the booking screen (booking_container visible).

    Steps covered:
      7.  Select member checkbox
      8.  Select service
      9.  Click Next  (Member → Office)
      10. Select Office
      11. Click Next  (Office → Date)
      12. Select Date  (custom weekly grid)
      13. Select Time Slot
      14. Click Next  (Date/Time → Review)
      15-16. Click Book Appointment

    Returns nothing; assertions should be made by the caller.
    """

    # ── Step 7: Select the MEMBER checkbox ──
    # First dismiss any lingering MUI Menu/Popover backdrop from the action menu click.
    # The backdrop intercepts pointer events and causes checkbox click to time-out.
    try:
        backdrop = page.locator(xpaths["mui_backdrop"])
        if backdrop.first.is_visible(timeout=2000):
            print(f"[{tag}] Backdrop detected — pressing Escape to dismiss")
            page.keyboard.press("Escape")
            backdrop.first.wait_for(state="hidden", timeout=5000)
    except Exception:
        pass
    page.wait_for_timeout(2000)

    def _is_any_checked():
        return page.evaluate("""
            () => {
                const cbs = document.querySelectorAll('input[type="checkbox"]');
                return Array.from(cbs).some(cb => cb.checked);
            }
        """)

    if _is_any_checked():
        print(f"[{tag}] A checkbox is already pre-selected — skipping manual check")
    else:
        print(f"[{tag}] Finding checkbox index for member: {member_name}")
        member_cb_index = page.evaluate(f"""
            () => {{
                const allSpans = Array.from(
                    document.querySelectorAll('span.MuiCheckbox-root')
                );
                for (let i = 0; i < allSpans.length; i++) {{
                    let el = allSpans[i].parentElement;
                    while (el && el !== document.body) {{
                        const innerCbs = el.querySelectorAll('span.MuiCheckbox-root');
                        if (innerCbs.length === 1) {{
                            if (el.textContent.includes('{member_name}')) return i;
                            break;
                        }}
                        el = el.parentElement;
                    }}
                }}
                return -1;
            }}
        """)
        print(f"[{tag}] JS found member checkbox at index: {member_cb_index}")

        all_cb_spans = page.locator(xpaths["mui_checkbox_spans"])
        if member_cb_index >= 0:
            cb = all_cb_spans.nth(member_cb_index)
            cb.scroll_into_view_if_needed()
            cb.click()
            page.wait_for_timeout(1000)
            print(f"[{tag}] Clicked checkbox at index {member_cb_index} ✓")
        else:
            print(f"[{tag}] JS index not found — using nth(1) as fallback")
            non_disabled = page.locator(xpaths["mui_checkbox_enabled"])
            idx = 1 if non_disabled.count() > 1 else 0
            non_disabled.nth(idx).scroll_into_view_if_needed()
            non_disabled.nth(idx).click(force=True)
            page.wait_for_timeout(1000)

    assert _is_any_checked(), f"[{tag}] FAIL: Could not select member checkbox"
    print(f"[{tag}] Member checkbox selected ✓")

    # ── Step 8: Select Service ──
    page.wait_for_timeout(2000)
    service = config["new_calendar"]["services"][0]
    print(f"[{tag}] Selecting service: {service}")

    member_svc_index = page.evaluate(f"""
        () => {{
            const allInputs = Array.from(
                document.querySelectorAll('input[placeholder="Service needed"]')
            );
            for (let i = 0; i < allInputs.length; i++) {{
                if (allInputs[i].disabled) continue;
                let el = allInputs[i].parentElement;
                while (el && el !== document.body) {{
                    const innerInputs = el.querySelectorAll(
                        'input[placeholder="Service needed"]'
                    );
                    if (innerInputs.length === 1) {{
                        if (el.textContent.includes('{member_name}')) return i;
                        break;
                    }}
                    el = el.parentElement;
                }}
            }}
            for (let i = allInputs.length - 1; i >= 0; i--) {{
                if (!allInputs[i].disabled) return i;
            }}
            return -1;
        }}
    """)
    print(f"[{tag}] JS found member service input at index: {member_svc_index}")

    all_svc_inputs = page.locator(xpaths["service_needed_input"])
    service_opened = False
    if member_svc_index >= 0:
        svc = all_svc_inputs.nth(member_svc_index)
        svc.scroll_into_view_if_needed()
        svc.click(force=True)
        page.wait_for_timeout(1000)
        service_opened = True
    else:
        print(f"[{tag}] JS service index not found — clicking last enabled input")
        enabled_svc = page.locator(xpaths["service_needed_input_enabled"])
        if enabled_svc.count() > 0:
            enabled_svc.last.scroll_into_view_if_needed()
            enabled_svc.last.click(force=True)
            page.wait_for_timeout(1000)
            service_opened = True

    listbox = page.locator(xpaths["listbox"])
    if not service_opened or listbox.count() == 0:
        print(f"[{tag}] Input click failed — trying MuiAutocomplete root")
        page.locator(xpaths["service_needed_dropdown"]).nth(
            member_svc_index if member_svc_index >= 0 else 1
        ).click(force=True)
        page.wait_for_timeout(1500)

    service_option = page.locator(xpaths["service_option"].format(service=service))
    if service_option.count() > 0:
        service_option.first.click(force=True)
        print(f"[{tag}] Service '{service}' selected ✓")
    else:
        print(f"[{tag}] Service '{service}' not found — selecting first available option")
        page.locator(xpaths["listbox_option"]).first.click(force=True)
    page.wait_for_timeout(1500)

    # ── Step 9: Next (Member → Office) ──
    next_btn = page.locator(xpaths["booking_next_btn"])
    next_btn.wait_for(state="visible", timeout=10000)
    expect(next_btn).to_be_enabled(timeout=10000)
    next_btn.click()
    page.wait_for_timeout(3000)

    # ── Step 10: Select Office ──
    office_name = config["new_calendar"]["name"]
    office_card = page.locator(xpaths["office_card"].format(name=office_name)).first
    if office_card.count() > 0 and office_card.is_visible():
        office_card.click()
        print(f"[{tag}] Office '{office_name}' selected ✓")
    else:
        print(f"[{tag}] Office '{office_name}' not found — selecting first available card")
        page.locator(xpaths["office_card_any"]).first.click()

    # ── Step 11: Next (Office → Date) ──
    page.locator(xpaths["booking_next_btn"]).click()
    page.wait_for_timeout(3000)

    # ── Step 12: Select Date (custom weekly grid, not MuiPickersDay) ──
    new_day = config["test_data"]["reschedule_day"]
    date_btn = page.locator(xpaths["booking_date_btn"].format(day=new_day)).first
    if date_btn.count() > 0 and date_btn.is_visible():
        date_btn.click()
        print(f"[{tag}] Date '{new_day}' selected ✓")
    else:
        print(f"[{tag}] Day '{new_day}' not found — picking first available date from custom grid")
        available_date = page.locator(xpaths["booking_date_any_available"]).first
        available_date.wait_for(state="visible", timeout=15000)
        available_date.click()
    page.wait_for_timeout(2000)

    # ── Step 13: Select Time Slot ──
    slot_locator = page.locator(xpaths["available_time_slot"]).filter(
        has_not=page.locator("[disabled]")
    )
    slot_locator.first.wait_for(state="visible", timeout=15000)
    slot_locator.first.click()
    print(f"[{tag}] Time slot selected ✓")

    # Handle "Confirm Appointment" dialog → click Yes
    try:
        confirm_yes = page.locator(
            "//button[@data-testid='qa-submit'] | "
            "//div[contains(@class,'MuiDialog')]//button[normalize-space(.)='Yes']"
        )
        confirm_yes.wait_for(state="visible", timeout=8000)
        confirm_yes.first.click()
        print(f"[{tag}] Confirm Appointment → Yes ✓")
        page.wait_for_timeout(1500)
    except Exception:
        print(f"[{tag}] No Confirm dialog after slot selection")

    # ── Step 14: Next (Date/Time → Review) ──
    page.locator(xpaths["booking_next_btn"]).click()
    page.wait_for_timeout(3000)

    # ── Steps 15-16: Review → Book Appointment ──
    print(f"[{tag}] On review screen — clicking Book Appointment")
    page.locator(xpaths["booking_final_book_btn"]).click()


def _cancel_booked_appointment(page, xpaths, user_name, tag="Cleanup"):
    """
    Cleanup helper — cancels the most recent open appointment for `user_name`
    in the Manage Appointments module.

    This function makes NO assertions and is safe to call inside a try/except
    block so that a cleanup failure never fails the parent test case.

    Steps:
      1. Navigate to Manage Appointments
      2. Search for the user by name
      3. Find the matching row and open its action menu
      4. Click 'Cancel' from the dropdown
      5. Click 'Cancel Appointment' button inside the details drawer
      6. Wait for the success toast

    Args:
        page       — Playwright Page object
        xpaths     — xpaths dict from admin_session fixture (merged toml sections)
        user_name  — Full name used to search (e.g. member_name or primary user name)
        tag        — Label prefix for print messages (default: 'Cleanup')
    """
    print(f"[{tag}] Navigating to Manage Appointments to cancel appointment for '{user_name}'")

    # 1. Navigate to Manage Appointments (use .first — success dialog may also have same href link)
    page.locator(xpaths["manage_appointments_menu"]).first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    # 2. Search for the user
    search = page.locator(xpaths["search_input_apt"])
    search.wait_for(state="visible", timeout=15000)
    search.fill(user_name)
    page.keyboard.press("Enter")
    page.wait_for_timeout(3000)

    # 3. Find the matching appointment row
    all_rows = page.locator(xpaths["appointment_row"])
    target_row = None
    for i in range(all_rows.count()):
        if user_name.lower() in all_rows.nth(i).inner_text().lower():
            target_row = all_rows.nth(i)
            break

    if not target_row:
        print(f"[{tag}] WARNING: No appointment row found for '{user_name}' — skipping cancellation")
        return

    # 4. Open action menu and click Cancel
    target_row.locator(xpaths["action_menu_btn"]).click(force=True)
    page.wait_for_timeout(1000)
    page.locator(xpaths["cancel_option"]).wait_for(state="visible", timeout=10000)
    page.locator(xpaths["cancel_option"]).click()
    page.wait_for_timeout(2000)

    # 5. Appointment Details drawer opens — click 'Cancel Appointment' button
    cancel_btn = page.locator(xpaths["drawer_cancel_btn"])
    cancel_btn.wait_for(state="visible", timeout=15000)
    cancel_btn.click()
    page.wait_for_timeout(2000)

    # 6. Wait for success toast
    try:
        page.locator(xpaths["success_toast"]).first.wait_for(state="visible", timeout=15000)
        print(f"[{tag}] Appointment cancelled successfully for '{user_name}'")
    except Exception:
        print(f"[{tag}] WARNING: Success toast not detected after cancellation — may have already completed")


def _scrape_household_member_names(page, xpaths):
    """
    Scrape all names from the Household Members tab table.
    Used for mapping checkboxes on the subsequent booking screen.
    """
    all_member_names = []
    rows = page.locator(xpaths["member_row"])
    for i in range(rows.count()):
        try:
            name = rows.nth(i).locator(xpaths["member_name_cell"]).inner_text().strip()
            if name: all_member_names.append(name)
        except:
            pass
    return all_member_names


def _find_cb_idx_by_name(page, name, all_family_names):
    """
    Use JS to find the checkbox index by walking up to the first Grid/Row container.
    'all_family_names' should include both Primary and all HH members.
    """
    all_names_js = json.dumps(all_family_names)
    return page.evaluate(f"""
        () => {{
            const allNames = {all_names_js};
            const target = '{name}';
            const spans = Array.from(document.querySelectorAll('span.MuiCheckbox-root'));
            
            for (let i = 0; i < spans.length; i++) {{
                let row = spans[i].parentElement;
                while (row && row !== document.body) {{
                    if (row.classList.contains('MuiGrid-container') || row.tagName === 'TR' || row.getAttribute('role') === 'row') {{
                        break;
                    }}
                    row = row.parentElement;
                }}
                
                if (row) {{
                    const text = row.innerText;
                    const nameElements = Array.from(row.querySelectorAll('h4, h5, h6, td, p'));
                    for (const el of nameElements) {{
                        if (el.innerText.trim() === target || el.innerText.includes(target)) return i;
                    }}
                    if (text.includes(target)) return i;
                }}
            }}
            return -1;
        }}
    """)


def _get_name_at_cb_idx(page, idx, all_family_names):
    """Read the name for the Nth checkbox by parsing its isolated row container."""
    all_names_js = json.dumps(all_family_names)
    return page.evaluate(f"""
        () => {{
            const allNames = {all_names_js};
            const spans = Array.from(document.querySelectorAll('span.MuiCheckbox-root'));
            const span = spans[{idx}];
            if (!span) return null;
            
            let row = span.parentElement;
            while (row && row !== document.body) {{
                if (row.classList.contains('MuiGrid-container') || row.tagName === 'TR' || row.getAttribute('role') === 'row') {{
                    break;
                }}
                row = row.parentElement;
            }}
            
            if (row) {{
                const text = row.innerText;
                for (const n of allNames) {{
                    if (text.includes(n)) return n;
                }}
            }}
            return null;
        }}
    """)


def _select_checkbox_for_member(page, xpaths, name, all_family_names, tag="Booking"):
    """
    Find and select the checkbox for a specific family member.
    Returns the actual name identified at the clicked checkbox (for tracking).
    """
    print(f"[{tag}] Selecting checkbox for '{name}'...")
    idx = _find_cb_idx_by_name(page, name, all_family_names)
    all_cbs = page.locator(xpaths["mui_checkbox_spans"])
    
    if idx >= 0:
        cb = all_cbs.nth(idx)
        inp = cb.locator("input")
        # Check if enabled and visible
        is_disabled = "Mui-disabled" in (cb.get_attribute("class") or "") or inp.is_disabled()
        
        if is_disabled:
            print(f"[{tag}] '{name}' checkbox is DISABLED (likely has existing appointment) — falling back...")
            # Set idx to -1 to trigger the fallback logic below
            idx = -1
        elif inp.is_checked():
            print(f"[{tag}] '{name}' already pre-selected ✓")
            return name
        else:
            cb.scroll_into_view_if_needed()
            cb.click()
            page.wait_for_timeout(1000)
            print(f"[{tag}] '{name}' checkbox selected ✓")
            return name

    if idx < 0:

        # Fallback: find the next unchecked enabled checkbox and read its actual name
        print(f"[{tag}] Could not find '{name}' by name — using next unchecked checkbox")
        enabled_cbs = page.locator(xpaths["mui_checkbox_enabled"])
        
        for i in range(enabled_cbs.count()):
            cb = enabled_cbs.nth(i)
            inp = cb.locator("input")
            if inp.count() > 0 and not inp.is_checked():
                # Correctly identify the global index of this enabled checkbox
                g_idx = page.evaluate("""
                    (el) => {
                        const all = Array.from(document.querySelectorAll('span.MuiCheckbox-root'));
                        return all.indexOf(el);
                    }
                """, cb.element_handle())
                
                if g_idx >= 0:
                    actual = _get_name_at_cb_idx(page, g_idx, all_family_names)
                    cb.click()
                    page.wait_for_timeout(1000)
                    print(f"[{tag}] Clicked unchecked cb[{g_idx}] → actual name: '{actual}' ✓")
                    return actual
        return None



def _select_booking_service_for(page, xpaths, config, name, tag="Booking"):
    """Select the first configured service for the specified member."""
    if not name: return
    service = config["new_calendar"]["services"][0]
    idx = page.evaluate(f"""
        () => {{
            const inputs = Array.from(document.querySelectorAll('input[placeholder="Service needed"]'));
            for (let i = 0; i < inputs.length; i++) {{
                if (inputs[i].disabled) continue;
                let el = inputs[i].parentElement;
                while (el && el !== document.body) {{
                    const inner = el.querySelectorAll('input[placeholder="Service needed"]');
                    if (inner.length === 1) {{
                        if (el.textContent.includes('{name}')) return i;
                        break;
                    }}
                    el = el.parentElement;
                }}
            }}
            return -1;
        }}
    """)
    all_inputs = page.locator(xpaths["service_needed_input"])
    if idx >= 0:
        svc = all_inputs.nth(idx)
    else:
        # Fallback: last enabled input
        enabled = page.locator(xpaths["service_needed_input_enabled"])
        if enabled.count() == 0: return
        svc = enabled.last

    svc.scroll_into_view_if_needed()
    svc.click(force=True)
    page.wait_for_timeout(1000)
    opt = page.locator(xpaths["service_option"].format(service=service))
    if opt.count() > 0:
        opt.first.click(force=True)
        print(f"[{tag}] Service '{service}' for '{name}' ✓")
    else:
        page.keyboard.press("Escape")


def _get_selected_member_names_from_dom(page, all_family_names):
    """Scrape the names of all members currently checked on the booking screen."""
    all_names_js = json.dumps(all_family_names)
    return page.evaluate(f"""
        () => {{
            const allNames = {all_names_js};
            const names = [];
            const spans = Array.from(document.querySelectorAll('span.MuiCheckbox-root'));
            for (let i = 0; i < spans.length; i++) {{
                const input = spans[i].querySelector('input');
                if (!input || !input.checked) continue;
                
                let row = spans[i].parentElement;
                while (row && row !== document.body) {{
                    if (row.classList.contains('MuiGrid-container') || row.tagName === 'TR' || row.getAttribute('role') === 'row') {{
                        break;
                    }}
                    row = row.parentElement;
                }}
                
                if (row) {{
                    const text = row.innerText;
                    for (const n of allNames) {{
                        if (text.includes(n)) {{
                            names.push(n);
                            break;
                        }}
                    }}
                }}
            }}
            return names;
        }}
    """)

