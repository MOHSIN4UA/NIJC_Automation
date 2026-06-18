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
    "_fill_basic_calendar_fields",
    "_click_chip_by_date_label",
    "_select_time_robust",
    "_fill_remaining_form_with_valid_data",
    "_open_day_config_from_preview",
    "_get_timestamped_filename",
    "_click_save_and_wait",
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
    try:
        inp.scroll_into_view_if_needed()
    except Exception as e:
        # Element may be detached/re-rendering. Re-resolve and retry once.
        print(f"[Clock] scroll_into_view race ({e}) — re-resolving locator")
        page.wait_for_timeout(500)
        inp = page.locator(input_xpath).first
        try:
            inp.scroll_into_view_if_needed()
        except Exception:
            pass

    dialog = None
    clock_icon_xpath = input_xpath + xpaths["clock_icon_suffix"]
    dialog_selector = xpaths["dialog_visible"]

    for i in range(5):
        print(f"[Clock] Triggering {time_str} (attempt {i+1})...")
        page.wait_for_timeout(1000)

        # Try different triggers: Input, Icon, then JS Evaluate. Wrap each
        # in try/except so a 'not visible' / 'detached' failure on one
        # strategy falls through to the next instead of aborting the loop.
        try:
            if i == 0 or i == 2:
                inp.click(force=True)
            elif i == 1 or i == 3:
                icon = page.locator(clock_icon_xpath).first
                target = icon if icon.count() > 0 else inp
                try:
                    target.click(force=True)
                except Exception:
                    handle = target.element_handle()
                    if handle:
                        page.evaluate("el => el.click()", handle)
            else:
                handle = inp.element_handle()
                if handle:
                    page.evaluate("el => el.click()", handle)
        except Exception as e:
            print(f"[Clock] Trigger attempt {i+1} failed: {e}")

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
    """Wait for the MUI date picker popper/dialog to become visible.
    Some MUI builds render the picker as a [role='dialog'] instead of a
    popper, and some inputs are readonly so clicking the input doesn't open
    the picker — only the sibling calendar-icon adornment does. Cover both."""
    picker_selector = (
        "css=.MuiPickerPopper-paper, .MuiPickersPopper-root, .MuiDateRangePicker-root, "
        "[role='dialog']:has(.MuiPickersCalendarHeader-root), "
        "[role='dialog']:has(div[role='grid'])"
    )
    picker = page.locator(picker_selector).first
    try:
        picker.wait_for(state="visible", timeout=timeout)
        page.wait_for_timeout(400)
        return
    except Exception:
        pass

    if input_locator:
        # Try clicking the sibling calendar-icon img adornment — for readonly
        # inputs, the input click is a no-op but the img click opens the
        # picker.
        try:
            input_locator.evaluate(
                "el => { const adorn = el.closest('.MuiInputBase-root')?.querySelector('img[role], img, [class*=adornment] *'); if (adorn) adorn.click(); }"
            )
            picker.wait_for(state="visible", timeout=timeout)
            page.wait_for_timeout(400)
            return
        except Exception:
            pass
        # Last resort: click the input again
        print("[Picker] Not visible, retrying click...")
        input_locator.click(force=True)
        picker.wait_for(state="visible", timeout=timeout)
    else:
        picker.wait_for(state="visible", timeout=timeout)
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
    """Ensure we are on the Manage Calendars tab by clicking menu if needed.
    networkidle hangs on this SPA (continuous polling), so we wait for the
    page header to read 'Manage Calendars' instead.
    """
    header = page.locator(xpaths["page_header"]).first
    try:
        if header.count() == 0 or "Manage Calendars" not in header.inner_text(timeout=3000):
            print("[Nav] Clicking Manage Calendars menu")
            page.locator(xpaths["manage_calendars_menu"]).click()
            try:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            page.wait_for_timeout(1000)
    except Exception:
        page.locator(xpaths["manage_calendars_menu"]).click()
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(1000)

    tab_btn = page.locator(xpaths["tab_manage_calendars"])
    if tab_btn.count() > 0:
        tab_btn.click()
        page.wait_for_timeout(1000)

    # Clear any inherited search/filter state from the prior test. A leftover
    # calendar-name search (e.g. "My Test Calendar - Indiana XXXX") collapses
    # the listing to "No records found" and breaks every downstream test that
    # tries to operate on a row.
    try:
        reset_btn = page.locator("xpath=//button[normalize-space(.)='Reset' or contains(., 'Reset')]").first
        if reset_btn.count() > 0 and reset_btn.is_visible():
            reset_btn.click(timeout=2000)
            page.wait_for_timeout(500)
    except Exception:
        pass


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


# ---------------------------------------------------------------------------
# User and Appointment Helpers (NIJC Admin)
# ---------------------------------------------------------------------------

def _navigate_to_users(page, xpaths):
    """Ensure we are on the User Management list page with a clean search box."""
    if "/management/users/list" not in page.url:
        print("[Nav] Navigating to User Management")
        page.locator(xpaths["users_menu"]).click()
        page.wait_for_load_state("networkidle")
    page.wait_for_selector(xpaths["user_row"], timeout=15000)
    # Clear any leftover search filter from a prior test so the table shows
    # the full user list (otherwise iteration over rows can return 0 or stale).
    try:
        search = page.locator(xpaths["search_input_user"]).first
        if search.input_value():
            search.fill("")
            page.keyboard.press("Enter")
            page.wait_for_timeout(1500)
    except Exception:
        pass


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
    # Wait for the table to settle before picking the row — when a user was
    # just created, the list may re-render and detach our row mid-click.
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)
    row = page.locator(xpaths["user_row"]).filter(has_text=search_text).first
    row.wait_for(state="visible", timeout=10000)
    row.scroll_into_view_if_needed()
    row.locator(xpaths["user_action_btn"]).click(force=True)
    # Let the action-menu popover finish opening before targeting Book Appointment
    page.wait_for_timeout(800)
    book_opt = page.locator(xpaths["book_appointment_option"]).first
    book_opt.wait_for(state="visible", timeout=10000)
    # Guard against the "element was detached from DOM" race by retrying once
    try:
        book_opt.click(timeout=10000)
    except Exception:
        page.wait_for_timeout(1000)
        # Re-resolve and retry
        page.locator(xpaths["book_appointment_option"]).first.click(timeout=10000)
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
    """Click a top-level navigation menu link by its xpath key and wait for the
    page to settle. networkidle is unreliable on this SPA (continuous
    polling), so we wait for DOM load and then briefly for the URL/state to
    quiesce instead.
    """
    page.locator(xpaths[menu_key]).click()
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(800)


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

def _complete_booking_flow(page, xpaths, config, member_name=None, prefer_late_slot=False):
    """Completes the multi-step booking flow from the booking container.

    `prefer_late_slot=True` selects the LAST available time slot of the day
    instead of the first. Used by date-boundary tests (TC_023/024/052) that
    must deterministically book an afternoon slot — early-morning slots
    sometimes hide the To-boundary bug so the test result becomes flaky
    based on seed timing rather than product state.
    """
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

    # 5. Click Next (to Date Selection). If the office click didn't register
    # the app shows a "Missing Slot Selection / Please select an office" modal;
    # dismiss it, click the card via JS as a stronger fallback, and retry Next.
    page.locator(xpaths["booking_next_btn"]).click()
    page.wait_for_timeout(2500)
    missing = page.locator(xpaths["missing_slot_modal"]).first
    if missing.count() > 0 and missing.is_visible():
        print("[Booking] 'Please select an office' modal appeared — dismissing and retrying.")
        cancel_btn = page.locator(xpaths["missing_slot_modal_cancel_btn"]).first
        if cancel_btn.count() > 0:
            cancel_btn.click()
        page.wait_for_timeout(1000)
        page.evaluate(
            """({xpath}) => {
                const cards = Array.from(document.querySelectorAll('div.MuiCard-root')).filter(c => c.querySelector('h3'));
                if (cards.length) {
                    const c = cards[0];
                    (c.querySelector('h3') || c).click();
                }
            }""",
            {"xpath": ""},
        )
        page.wait_for_timeout(1500)
        page.locator(xpaths["booking_next_btn"]).click()
        page.wait_for_timeout(3000)
    else:
        page.wait_for_timeout(500)
    
    # 6. Select Date — prefer tomorrow's day-of-month (today + 1) so the test
    # always books a near-future appointment. Fall back to the first available
    # date in the visible weekly grid if tomorrow isn't bookable.
    from datetime import date as _date, timedelta as _td
    tomorrow_dt = _date.today() + _td(days=1)
    tomorrow_day = str(tomorrow_dt.day)
    selected_date_iso = None
    date_btn = page.locator(xpaths["booking_date_btn"].format(day=tomorrow_day)).first
    if date_btn.count() > 0 and date_btn.is_visible():
        date_btn.click()
        selected_date_iso = tomorrow_dt.isoformat()
        print(f"[Booking] Date (today+1) '{tomorrow_day}' selected ✓")
    else:
        print(f"[Booking] Day '{tomorrow_day}' not bookable — selecting first available date from custom grid.")
        available_date = page.locator(xpaths["booking_date_any_available"]).first
        available_date.wait_for(state="visible", timeout=15000)
        available_date.click()
    page.wait_for_timeout(2000)

    # 7. Select Time Slot. Date-boundary tests pass prefer_late_slot=True to
    # force the latest slot of the day — early-morning slots can mask the
    # To-boundary bug (slot's local-date == UTC-date), making the test flaky.
    slot_locator = page.locator(xpaths["available_time_slot"]).filter(has_not=page.locator("[disabled]"))
    captured_slot_text = None
    if slot_locator.count() > 0:
        target_slot = slot_locator.last if prefer_late_slot else slot_locator.first
        try:
            captured_slot_text = target_slot.inner_text(timeout=2000).strip()
        except Exception:
            captured_slot_text = None
        target_slot.click()
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

    return {"slot_text": captured_slot_text, "date_iso": selected_date_iso}

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
    # Email — short and dynamic. 6 hex chars = 16M possibilities, plenty
    # for any single test session and short enough to read at a glance.
    import uuid as _uuid
    unique_email = f"auto{_uuid.uuid4().hex[:6]}@example.com"
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


def _find_or_create_family_with_members(page, xpaths, config, min_eligible=2, max_pages=5, force_create=False, tc_id=None, last_name_tag=None):
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
    # Short, dynamic suffix for primary email + member naming.
    import uuid as _uuid
    ts = int(_time.time())  # 10-digit Unix seconds — still unique for any session
    rnd = _uuid.uuid4().hex[:6]

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
    
    # Last name — prefer `last_name_tag` (set by per-file callers like
    # 'BookAppointment' / 'ManageAppointment') so users seeded by each test
    # file are identifiable in QA data; fall back to config default.
    primary_last = last_name_tag if last_name_tag else ud["last_name"]
    page.locator(xpaths["last_name_input"]).click(force=True)
    page.locator(xpaths["last_name_input"]).press_sequentially(primary_last, delay=100)
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
    # Short and dynamic — `rnd` is a fresh 6-hex UUID slice per call
    primary_email = f"{email_prefix}{rnd}@example.com"
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

    # ── Step 12: Select Date — prefer tomorrow (today + 1), fallback to first
    # available date in the visible weekly grid.
    from datetime import date as _date, timedelta as _td
    tomorrow_day = str((_date.today() + _td(days=1)).day)
    date_btn = page.locator(xpaths["booking_date_btn"].format(day=tomorrow_day)).first
    if date_btn.count() > 0 and date_btn.is_visible():
        date_btn.click()
        print(f"[{tag}] Date (today+1) '{tomorrow_day}' selected ✓")
    else:
        print(f"[{tag}] Day '{tomorrow_day}' not bookable — picking first available date from custom grid")
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

    # 3. Find the matching appointment row.
    # Use tbody-scoped locator (excludes the header tr that shares MuiTableRow-root)
    # and Playwright's atomic filter+wait — earlier code did
    # `range(rows.count())` then `rows.nth(i).inner_text()`, which races: count()
    # captures one DOM state but a later nth(i) lookup can hang 60s if the table
    # re-renders between calls.
    target_row = page.locator(xpaths["tbody_appointment_row"]).filter(has_text=user_name).first
    try:
        target_row.wait_for(state="visible", timeout=15000)
    except Exception:
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


# ============================================================================
# Helpers moved from tests/test_manage_calendar.py (originally inline there).
# Tests still reach them transparently via `from tests.utils import *`.
# ============================================================================

def _get_timestamped_filename(base_name):
    return f"screenshots/{base_name}_{datetime.now().strftime('%H%M%S')}.jpg"

# ---------------------------------------------------------------------------
# Local Robust Helpers
# ---------------------------------------------------------------------------

def _fill_basic_calendar_fields(page, xpaths):
    """Fills mandatory fields for a new calendar."""
    # Wait for the first field to ensure page is loaded
    page.locator(xpaths["calendar_name_input"]).wait_for(state="visible", timeout=20000)
    
    page.locator(xpaths["zip_code_input"]).fill("46204")
    try:
        opt = page.locator(xpaths["ui_option"].format(val="46204")).first
        opt.wait_for(state="visible", timeout=5000)
        opt.click()
    except:
        page.keyboard.press("Enter")
    
    page.locator(xpaths["address_input"]).fill("200 E Washington St")
    page.locator(xpaths["services_input"]).click()
    # Use ui_option_all which is "//li" to select the first service
    page.locator(xpaths["ui_option_all"]).first.click()
    page.keyboard.press("Escape")

def _click_chip_by_date_label(page, date_obj):
    """Finds and clicks a day chip in the preview by its date object with robust navigation."""
    import re
    from datetime import datetime
    month_name = date_obj.strftime("%b") # e.g. "Jun"
    day_num = str(date_obj.day)
    
    print(f"[Preview] Target Date: {date_obj.strftime('%b %d, %Y')}")
    
    # Scroll to preview section
    preview_heading = page.locator("//h2[contains(., 'Preview')]").first
    preview_heading.scroll_into_view_if_needed()
    
    # Range text: e.g. "Apr 22, 2026 - May 12, 2026"
    header_locator = page.locator("//h2[contains(.,'Calendar Preview')]/following::p[contains(@class, 'MuiTypography-root')][1]")
    
    # Navigation loop
    for i in range(10): # Up to 10 periods (approx 7 months)
        try:
            header_text = header_locator.inner_text(timeout=5000).strip()
            print(f"[Preview] Current Range: '{header_text}'")
            
            # Parse header: "Apr 22, 2026 - May 12, 2026"
            parts = header_text.split(" - ")
            if len(parts) == 2:
                try:
                    # Clean up parts (sometimes they have extra whitespace or newlines)
                    p1 = parts[0].strip()
                    p2 = parts[1].strip()
                    
                    # Expected format "%b %d, %Y"
                    # If format changes, this might fail, so we wrap in try-except
                    start_dt = datetime.strptime(p1, "%b %d, %Y")
                    end_dt = datetime.strptime(p2, "%b %d, %Y")
                    
                    if start_dt <= date_obj <= end_dt:
                        print(f"[Preview] Date {date_obj.strftime('%Y-%m-%d')} is within displayed range.")
                        break
                    elif date_obj < start_dt:
                        print(f"[Preview] Target date is BEFORE current range. (Navigation only supports 'Next' for now)")
                        break 
                    else:
                        print(f"[Preview] Target date is AFTER current range. Clicking Next...")
                except Exception as e:
                    print(f"[Preview] Parsing error: {e}. Falling back to month name check.")
                    if month_name in header_text:
                        break
            else:
                if month_name in header_text:
                    break
        except Exception as e:
            print(f"[Preview] Header check failed: {e}")
        
        # Click Next button. The right arrow button in the preview header gets
        # disabled once the preview reaches the deactivation date, so we
        # detect that state and break the loop instead of hanging for 60s
        # on a click against a disabled button.
        next_btn = page.locator("//h2[contains(.,'Calendar Preview')]/following::button[contains(@class, 'MuiIconButton-root')]").last
        if not next_btn.is_visible():
            print("[Preview] Next button not found!")
            break
        try:
            if next_btn.is_disabled():
                print("[Preview] Next button disabled — end of preview range reached.")
                break
        except Exception:
            pass
        next_btn.click()
        page.wait_for_timeout(2000)

    # Click the h6 containing the day number within the preview context
    # We target the h6 that is likely the 'active' one in the grid
    day_h6 = page.locator(f"//h2[contains(.,'Calendar Preview')]/following::div[contains(@class, 'MuiBox-root')]//h6[text()='{day_num}']").first
    
    if day_h6.is_visible():
        print(f"[Preview] Clicking day {day_num}")
        day_h6.scroll_into_view_if_needed()
        day_h6.click(force=True)
        page.wait_for_timeout(2000)
        # Scroll a bit more to see the slots below
        page.evaluate("window.scrollBy(0, 400)")
        page.wait_for_timeout(1000)
    else:
        print(f"[Warning] Day {day_num} not found in preview grid!")
        page.screenshot(path=_get_timestamped_filename(f"MissingDay_{day_num}"))

        try:
            page.screenshot(path=f"FAIL_Preview_Day_{day_num}.png")
        except:
            pass

def _open_day_config_from_preview(page, xpaths):
    """Helper to scroll to preview, click an open day chip, and scroll to the bottom of the page using a saw-tooth approach."""
    from datetime import datetime
    TIMESTAMP = datetime.now().strftime("%H%M%S")
    
    print("[Preview-Flow] Scrolling to Calendar Preview heading")
    # If a save just ran (e.g. caller clicked Update Configuration/Proceed),
    # the NIJC-logo progress overlay can still be up and the Preview section
    # only renders once it clears. Wait for the loader to finish first.
    try:
        pb = page.locator(xpaths["progress_bar"])
        while pb.count() > 0 and pb.is_visible():
            page.wait_for_timeout(500)
    except Exception:
        pass
    preview_heading = page.get_by_text("Calendar Preview", exact=False).first
    try:
        preview_heading.wait_for(state="visible", timeout=15000)
    except:
        print("[Preview-Flow] Calendar Preview heading not found via get_by_text, trying generic locator")
        preview_heading = page.locator("xpath=//*[contains(text(), 'Preview')]").first
        preview_heading.wait_for(state="visible", timeout=15000)
    
    preview_heading.scroll_into_view_if_needed()
    page.wait_for_timeout(1500)

    # --- Scroll page down until the Open chip is clickable ---
    print("[Preview-Flow] Searching for Open day chip")
    open_day = page.locator(xpaths["calendar_open_day_chip"]).first
    
    # If no 'Open' chip, try to find ANY chip that isn't 'No Config'
    if open_day.count() == 0:
        print("[Preview-Flow] No 'Open' chip found, checking for ANY clickable chip...")
        open_day = page.locator("//h2[contains(.,'Calendar Preview')]/following::span[contains(@class,'MuiChip-label') and not(contains(.,'No Config'))]").first

    open_day.scroll_into_view_if_needed()
    page.wait_for_timeout(1000)
    open_day.click()
    print("[Preview-Flow] Chip clicked. Starting slow saw-tooth scroll to bottom.")
    page.wait_for_timeout(2000)

    # --- Slow "Saw-tooth" Scroll (Down and Up) to reveal Day Configuration AND Slot Rows ---
    print("[Preview-Flow] Scrolling PAGE slowly to reveal Day Configuration and Slot Rows...")
    drawer_title = page.locator(xpaths["day_config_title"]).first
    first_slot = page.locator(xpaths["slot_row"]).first
    found_title = False
    found_slots = False
    
    # Target: Scroll until all elements found
    for i in range(40): # Even more increments for slow rendering
        if not found_title and drawer_title.is_visible():
            print(f"[Preview-Flow] Day configuration title found at scroll attempt {i+1}")
            found_title = True
            
        if not found_slots and first_slot.is_visible():
            print(f"[Preview-Flow] Slot rows found at scroll attempt {i+1}")
            found_slots = True
            
        if found_title and found_slots:
            break
            
        # Scroll down 200px (smaller steps as requested "slowly")
        page.evaluate("window.scrollBy(0, 200)")
        page.wait_for_timeout(600)
            
        # Every 6 attempts, do a small scroll up (saw-tooth)
        if (i + 1) % 6 == 0:
            print("[Preview-Flow] Scrolling up slightly (saw-tooth step)")
            page.evaluate("window.scrollBy(0, -150)")
            page.wait_for_timeout(400)
    
    if not found_slots:
        print("[Preview-Flow] Slots not found by slow scroll, trying PageDown loop...")
        for _ in range(8):
            if first_slot.is_visible(): 
                found_slots = True
                break
            page.keyboard.press("PageDown")
            page.wait_for_timeout(800)
            if not found_title and drawer_title.is_visible(): found_title = True

    # Final confirmation and scroll into view
    try:
        drawer_title.wait_for(state="attached", timeout=5000)
        drawer_title.scroll_into_view_if_needed()
        print("[Preview-Flow] Day configuration section confirmed.")
        
        # Wait longer for slots as they are the meat of the section
        first_slot.wait_for(state="visible", timeout=15000)
        first_slot.scroll_into_view_if_needed()
        print("[Preview-Flow] Slot rows confirmed.")
    except Exception as e:
        print(f"[Preview-Flow] ERROR/Warning: Could not confirm all elements: {e}")
        try:
            page.screenshot(path=f"screenshots/FAIL_Elements_Not_Found_{TIMESTAMP}.jpg")
        except: pass
        if not found_title:
            raise Exception("Day Configuration title not found after scroll")
        # If slots still not found but title is, we might let it proceed to see if it's a specific TC issue

        # If slots still not found but title is, we might let it proceed to see if it's a specific TC issue

def _select_time_robust(page, input_xpath, time_str, ok_btn_xpath, xpaths):
    """Legacy entry point — delegates to select_time_via_clock which now
    follows the verified AM/PM-first → reopen → hour → > arrow → minute
    workflow (see feedback_clock_picker_workflow memory)."""
    print(f"[Clock-Robust] Triggering {time_str} for {input_xpath}")
    return select_time_via_clock(page, input_xpath, time_str, ok_btn_xpath, xpaths)


def _click_save_and_wait(page, xpaths, button_xpath_key="update_configuration_btn"):
    """Click the Proceed / Update Configuration button and then block until
    the NIJC-logo progress-bar overlay clears. Mandatory after every save
    per user guidance (`while pb.is_visible(): page.wait_for_timeout(500)`)
    — otherwise downstream assertions race the loader and time out.

    Args:
        page: Playwright page
        xpaths: xpaths dict (merged sections)
        button_xpath_key: which xpath to use for the button (default:
            "update_configuration_btn"). Pass a different key for the
            User Dashboard or other variants.
    """
    page.locator(xpaths[button_xpath_key]).click(force=True)
    try:
        pb = page.locator(xpaths["progress_bar"])
        while pb.count() > 0 and pb.is_visible():
            page.wait_for_timeout(500)
    except Exception:
        pass

def _fill_remaining_form_with_valid_data(page, xpaths, config):
    """Helper to fill valid data in all required fields except the one being tested."""
    cal_data = config["new_calendar"]

    # Fill Address and ZIP using unified helper
    _fill_calendar_address(page, xpaths, zip_code=cal_data["zip"], address_line1=cal_data["address"])

    # Services (if empty)
    svc_loc = page.locator(xpaths["services_input"])
    if not svc_loc.input_value():
        svc_loc.click()
        page.locator(xpaths["ui_option_all"]).first.click()
        page.keyboard.press("Escape")

    # Dates are usually pre-filled with today/future, but ensure they are set
    # Operating hours are pre-filled with 9-5 usually


def _ensure_edit_page_open(page, xpaths, config):
    """Helper to ensure we are on the edit page of the first available calendar."""
    _ensure_manage_calendars_tab(page, xpaths)
    page.wait_for_selector(xpaths["manage_calendar_row"], timeout=20000)
    page.evaluate(xpaths["horizontal_scroll_table_script"])
    page.wait_for_timeout(1000)
    action_btn = page.locator(xpaths["calendar_action_menu"]).first
    action_btn.click(force=True)
    edit_opt = page.locator(xpaths["edit_option"])
    try:
        edit_opt.wait_for(state="visible", timeout=5000)
    except:
        print("[Helper] Re-clicking action menu...")
        action_btn.click(force=True)
    
    edit_opt.wait_for(state="visible", timeout=15000)
    edit_opt.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

# Portal Helpers
# ---------------------------------------------------------------------------
def _navigate_to_portal_calendar(page, xpaths, config, calendar_name=None):
    """Helper to navigate to a specific calendar in the User Portal."""
    target_cal_name = calendar_name if calendar_name else config["new_calendar"]["name"]

    print(f"[Portal] Navigating to appointment flow for: {target_cal_name}")
    
    page.locator(xpaths["new_appointment_btn"]).wait_for(state="visible", timeout=30000)
    page.locator(xpaths["new_appointment_btn"]).click()
    page.wait_for_load_state("networkidle")
    
    # Select Member (Checkbox)
    print("[Portal] Selecting first member")
    member_cb = page.locator(xpaths["checkbox_member"]).first
    member_cb.wait_for(state="visible", timeout=15000)
    member_cb.click()
    page.wait_for_timeout(500)

    # Select Service
    svc_input = page.locator(xpaths["select_service"]).first
    svc_input.wait_for(state="visible", timeout=15000)
    
    service_name = "Adjustment of Status"
    if "new_calendar" in config and "services" in config["new_calendar"]:
        service_name = config["new_calendar"]["services"][0]
        
    print(f"[Portal] Selecting service: {service_name}")
    
    # User's requested click-based selection
    svc_input.click()
    opt = page.locator(xpaths["service_option"].format(service=service_name)).first
    opt.wait_for(state="visible", timeout=15000)
    opt.click(force=True)

    page.locator(xpaths["next_btn"]).click()
    
    # Wait for office selection step marker before scanning cards
    print("[Portal] Waiting for office selection step marker...")
    expect(page.locator(xpaths["office_selection_marker"])).to_be_visible(timeout=50000)
    page.wait_for_timeout(2000)
    
    # Select Office/Calendar - ROBUST SEARCH
    print(f"[Portal] Searching for calendar card '{target_cal_name}'...")
    found = False
    for attempt in range(3):
        for i in range(15):
            # Scan names for logging
            names = page.locator("//h3[contains(@class, 'MuiTypography-h6')]").all_text_contents()
            print(f"[Portal] Attempt {attempt+1}, Scroll {i+1}: Calendars: {names}")
            
            # Based on DOM inspection, the name is in an h3 tag.
            # We target the heading directly for precision.
            card_heading = page.get_by_role("heading", name=target_cal_name, exact=True)
            
            if card_heading.is_visible():
                print(f"[Portal] Found calendar heading '{target_cal_name}'")
                card_heading.scroll_into_view_if_needed()
                card_heading.click()
                
                # Brief wait for selection to be processed
                page.wait_for_timeout(2000)
                
                found = True
                break
            page.evaluate("window.scrollBy(0, 500)")
            page.wait_for_timeout(800)
            
        if found: break
        if attempt < 2:
            print(f"[Portal] Not found. Navigating home and retrying...")
            page.goto("https://uat-user.azurehosted.app/home")
            page.wait_for_load_state("networkidle")
            
            # Restart flow
            page.locator(xpaths["new_appointment_btn"]).click()
            page.wait_for_load_state("networkidle")
            page.locator(xpaths["checkbox_member"]).first.click()
            
            # Service
            page.locator(xpaths["select_service"]).first.click()
            page.locator(xpaths["service_option"].format(service=service_name)).first.wait_for(state="visible", timeout=15000)
            page.locator(xpaths["service_option"].format(service=service_name)).first.click(force=True)
            page.locator(xpaths["next_btn"]).click()
            
            expect(page.locator(xpaths["office_selection_marker"])).to_be_visible(timeout=30000)
            page.wait_for_timeout(2000)

    if not found:
        pytest.fail(f"Could not find calendar card '{target_cal_name}' in portal.")
        
    page.locator(xpaths["next_btn"]).click()
    page.wait_for_load_state("networkidle")
