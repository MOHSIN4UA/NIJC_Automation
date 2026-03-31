import asyncio
import os
import toml
from playwright.sync_api import sync_playwright

def get_modal_dom():
    config = toml.load("conf.toml")
    xpaths = toml.load("xpath.toml")["admin_portal"]
    
    with sync_playwright() as p:
        user_data_dir = "user_data"
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=True
        )
        page = context.pages[0] if context.pages else context.new_page()
        
        # Navigate to calendars
        page.goto("https://uat-admin.azurehosted.app/scheduling/manage-calendars")
        page.wait_for_load_state("networkidle")
        
        # Click Holidays tab
        page.locator(xpaths["tab_manage_holidays"]).click()
        page.wait_for_timeout(2000)
        
        # Open modal
        modal_title_xpath = xpaths["holiday_modal_title"]
        if not page.locator(modal_title_xpath).is_visible():
            page.locator(xpaths["holiday_add_new_btn"]).first.click(force=True)
            page.wait_for_timeout(2000)
        
        # Fill name
        page.locator(xpaths["holiday_name_input"]).fill("DOM_DEBUG")
        
        # Set Dates via Calendar
        page.locator(xpaths["holiday_start_date_input"]).click()
        page.wait_for_timeout(1000)
        page.locator(xpaths["holiday_calendar_day"].format(day="28")).first.click()
        
        page.locator(xpaths["holiday_end_date_input"]).click()
        page.wait_for_timeout(1000)
        page.locator(xpaths["holiday_calendar_day"].format(day="30")).first.click()
        
        page.wait_for_timeout(2000)
        
        # Get DOM
        with open("holiday_modal_latest.html", "w") as f:
            f.write(page.content())
        
        print("Captured holiday_modal_latest.html")
        
        # Check if Submit works
        page.locator(xpaths["holiday_submit_btn"]).first.click(force=True)
        page.wait_for_timeout(2000)
        if page.locator(modal_title_xpath).is_visible():
            print("Modal STILL visible after submit. Checking for errors...")
            # Capture screenshot
            page.screenshot(path="submit_failure.png")
        else:
            print("Modal closed after submit.")
            
        context.close()

if __name__ == "__main__":
    get_modal_dom()
