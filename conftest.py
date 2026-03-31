import pytest
import toml
import os, shutil
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def config():
    return toml.load("conf.toml")

@pytest.fixture(scope="session")
def xpaths():
    return toml.load("xpath.toml")

@pytest.fixture(scope="session")
def admin_session(playwright, config, xpaths):
    """
    Fixture for Admin Portal session.
    Uses a persistent browser context to save session data.
    """
    admin_config = config["admin"]
    playwright_config = config["playwright"]
    admin_xpaths = xpaths["admin_portal"]
    credentials = config["credentials"]
    target_url = admin_config["url"]
    user_data_dir = "user_data"

    # Pre-launch cleanup: Terminate any stale Chromium processes and remove SingletonLock
    try:
        if os.path.exists(user_data_dir):
            import subprocess
            # Brute force kill any stale chromium processes using this data dir
            subprocess.run(["pkill", "-f", "chromium"], capture_output=True)
            page_lock = os.path.join(user_data_dir, "SingletonLock")
            if os.path.exists(page_lock):
                os.remove(page_lock)
                print(f"[Fixture] Cleared stale SingletonLock: {page_lock}")
    except Exception as e:
        print(f"[Fixture] Cleanup warning: {e}")

    # Launch a persistent browser context
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        headless=playwright_config.get("headless", False),
        viewport=playwright_config.get("viewport", {"width": 1280, "height": 720})
    )
    page = context.pages[0] if context.pages else context.new_page()

    _perform_login(page, target_url, admin_xpaths, credentials)

    # Wait for dashboard to be ready
    print("Confirming dashboard is loaded...")
    try:
        page.wait_for_selector(admin_xpaths["dashboard_welcome_text"], timeout=30000)
        print("Dashboard loaded successfully.")
    except:
        print("Warning: Dashboard welcome text not found in 30s. Continuing anyway.")

    yield page, admin_xpaths, config

    context.close()


# ---------------------------------------------------------------------------
# Login logic (always runs the full login flow)
# ---------------------------------------------------------------------------

def _perform_login(page, target_url, admin_xpaths, credentials):
    """Navigate to the app and run the login flow if needed."""
    print(f"[Login] Navigating to {target_url}...")
    page.goto(target_url)

    # Step 0: Check if session is already active
    try:
        page.wait_for_url("**/dashboard*", timeout=10000)
        print("[Login] Session is already active (Dashboard detected). Skipping.")
        return
    except:
        if "/dashboard" in page.url:
            print("[Login] URL contains dashboard. Skipping login flow.")
            return

    page.wait_for_load_state("domcontentloaded")

    # Step 1: Wait for the SSO login button and click it
    print("[Login] Waiting for SSO login button...")
    try:
        # Check if already logged in first
        if "/dashboard" in page.url: return

        page.wait_for_selector(admin_xpaths["login_with_sso"], timeout=15000)
        print("[Login] Clicking 'Login with SSO'...")
        page.locator(admin_xpaths["login_with_sso"]).click()
    except Exception as e:
        if "/dashboard" in page.url:
            print("[Login] Dashboard reached before SSO click. Continuing.")
            return
        print(f"[Login] SSO button not found/interrupted: {e} — current URL: {page.url}")

    # Step 2: Wait for Microsoft login page
    print("[Login] Waiting for Microsoft login page...")
    try:
        page.wait_for_url("**/login.microsoftonline.com/**", timeout=20000)
        page.wait_for_load_state("networkidle", timeout=30000)
        print(f"[Login] On MS page: {page.url}")
    except Exception as e:
        if "/dashboard" in page.url:
            print("[Login] Landed on dashboard instead of MS login (session active).")
            return
        raise e

    # Handle "Pick an account" / Account Selection if it appears
    try:
        # Look for the email text in the list of accounts
        account_selector = f"text={credentials['admin_email']}"
        if page.locator(account_selector).is_visible(timeout=5000):
            print(f"[Login] Selecting existing account: {credentials['admin_email']}...")
            page.locator(account_selector).click()
            page.wait_for_load_state("domcontentloaded")
            # If we clicked an account, we might skip the email input step
    except:
        pass

    # Step 3: Enter email
    try:
        email_field = page.locator(admin_xpaths["email_input"])
        email_field.wait_for(state="visible", timeout=8000)
        print("[Login] Entering email...")
        email_field.fill(credentials["admin_email"])
        page.locator(admin_xpaths["next_button"]).click()
        page.wait_for_load_state("domcontentloaded")
    except:
        print("[Login] Email field not found — may already be pre-filled or account selected.")

    # Step 4: Enter password
    try:
        password_field = page.locator(admin_xpaths["password_input"])
        password_field.wait_for(state="visible", timeout=15000)
        print("[Login] Entering password...")
        password_field.fill(credentials["admin_password"])
        page.locator(admin_xpaths["sign_in_button"]).click()
        page.wait_for_load_state("domcontentloaded")
    except:
        print(f"[Login] Password field not found. Current URL: {page.url}")

    # Step 5: Handle 'Stay signed in?' if it appears
    try:
        stay_btn = page.locator(admin_xpaths["stay_signed_in_yes"])
        stay_btn.wait_for(state="visible", timeout=5000)
        print("[Login] Clicking 'Stay signed in: Yes'...")
        stay_btn.click()
    except:
        pass  # MFA screen or not shown

    # Step 6: Wait for MFA approval (up to 2 minutes)
    print("\n" + "="*60)
    print("  *** ACTION REQUIRED: APPROVE MFA ON YOUR PHONE ***")
    print("  DO NOT CLOSE THE BROWSER WINDOW.")
    print("  Waiting up to 2 minutes for dashboard to appear...")
    print("="*60 + "\n")
    page.wait_for_url("**/dashboard", timeout=120000)
    page.wait_for_selector(admin_xpaths["dashboard_welcome_text"], timeout=30000)
    print("[Login] Login successful! Landed on dashboard.")


# ---------------------------------------------------------------------------
# Standalone runner — python conftest.py
# ---------------------------------------------------------------------------

def run_auth_setup():
    config = toml.load("conf.toml")
    admin_xpaths = toml.load("xpath.toml")["admin_portal"]
    credentials = config["credentials"]
    user_data_dir = "user_data"
    target_url = config["admin"]["url"]

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            viewport={"width": 1280, "height": 720}
        )
        page = context.pages[0] if context.pages else context.new_page()

        _perform_login(page, target_url, admin_xpaths, credentials)

        context.close()


if __name__ == "__main__":
    run_auth_setup()
