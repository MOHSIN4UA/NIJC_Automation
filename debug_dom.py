import toml
import os
from playwright.sync_api import sync_playwright

def _perform_login(page, target_url, admin_xpaths, credentials):
    print(f"[Login] Navigating to {target_url}...")
    page.goto(target_url)
    try:
        page.wait_for_url("**/dashboard", timeout=8000)
        print("[Login] Session is active. Skipping login.")
        return
    except:
        pass
    page.wait_for_load_state("domcontentloaded")
    print("[Login] Waiting for SSO login button...")
    try:
        page.wait_for_selector(admin_xpaths["login_with_sso"], timeout=15000)
        page.locator(admin_xpaths["login_with_sso"]).click()
    except Exception as e:
        print(f"[Login] SSO button not found: {e}")
    
    page.wait_for_url("**/login.microsoftonline.com/**", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=30000)
    
    try:
        account_selector = f"text={credentials['admin_email']}"
        if page.locator(account_selector).is_visible(timeout=5000):
            page.locator(account_selector).click()
            page.wait_for_load_state("domcontentloaded")
    except:
        pass

    try:
        email_field = page.locator(admin_xpaths["email_input"])
        email_field.wait_for(state="visible", timeout=8000)
        email_field.fill(credentials["admin_email"])
        page.locator(admin_xpaths["next_button"]).click()
        page.wait_for_load_state("domcontentloaded")
    except:
        pass

    try:
        password_field = page.locator(admin_xpaths["password_input"])
        password_field.wait_for(state="visible", timeout=15000)
        password_field.fill(credentials["admin_password"])
        page.locator(admin_xpaths["sign_in_button"]).click()
        page.wait_for_load_state("domcontentloaded")
    except:
        pass

    try:
        stay_btn = page.locator(admin_xpaths["stay_signed_in_yes"])
        stay_btn.wait_for(state="visible", timeout=5000)
        stay_btn.click()
    except:
        pass

    page.wait_for_url("**/dashboard", timeout=30000)
    page.wait_for_selector(admin_xpaths["dashboard_welcome_text"], timeout=30000)

def main():
    config = toml.load("conf.toml")
    xpaths = toml.load("xpath.toml")
    admin_xpaths = xpaths["admin_portal"]
    credentials = config["credentials"]
    user_data_dir = "user_data"
    target_url = config["admin"]["url"]

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=True,
            viewport={"width": 1280, "height": 720}
        )
        page = context.pages[0] if context.pages else context.new_page()

        _perform_login(page, target_url, admin_xpaths, credentials)

        print("[Debug] Navigating to Manage Calendars...")
        page.locator(admin_xpaths["manage_calendars_menu"]).click()
        page.wait_for_load_state("networkidle")

        print("[Debug] Switching to Manage Holidays tab...")
        page.locator(xpaths["admin_portal"]["tab_manage_holidays"]).first.click()
        page.wait_for_timeout(3000)

        print("[Debug] Clicking 'Add New Holiday' button...")
        btn = page.locator(xpaths["admin_portal"]["holiday_add_new_btn"]).first
        btn.click(force=True)
        page.wait_for_timeout(3000)

        print("[Debug] Clicking Start Date input to open picker...")
        page.locator(xpaths["admin_portal"]["holiday_start_date_input"]).click()
        page.wait_for_timeout(3000)

        print("[Debug] Capturing Screenshot...")
        screenshot_path = os.path.abspath("holiday_picker_debug.png")
        page.screenshot(path=screenshot_path)
        print(f"[Debug] Screenshot saved to: {screenshot_path}")

        print("[Debug] Dumping DOM...")
        dom_content = page.content()
        with open("holiday_picker_dom.html", "w") as f:
            f.write(dom_content)
        print("[Debug] DOM dumped to: holiday_picker_dom.html")

        context.close()

if __name__ == "__main__":
    main()
