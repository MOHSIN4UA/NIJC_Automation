import pytest
import toml
import os, shutil
from datetime import datetime
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
    page.set_default_navigation_timeout(60000)
    page.set_default_timeout(60000)

    _perform_login(page, target_url, admin_xpaths, credentials)

    # Wait for dashboard to be ready
    print("Confirming dashboard is loaded...")
    for attempt in range(3):
        try:
            page.wait_for_selector(admin_xpaths["dashboard_welcome_text"], timeout=45000)
            print("Dashboard loaded successfully.")
            break
        except:
            print(f"Warning: Dashboard welcome text not found (attempt {attempt+1}). Reloading...")
            page.reload()
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)

    yield page, admin_xpaths, config

    context.close()


# ---------------------------------------------------------------------------
# User Dashboard session — opens a NEW TAB, logs in only when requested
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def user_dashboard_session(admin_session):
    """
    Opens the User Dashboard in a new browser tab and logs in if needed.
    Only executes when a test explicitly requests this fixture (not autouse).
    Yields: (user_page, user_xpaths, config)
    """
    import toml

    page, admin_xpaths, config = admin_session

    # Load user_dashboard xpaths from the xpath.toml
    try:
        mc_data = toml.load("xpath.toml")
        user_xpaths = mc_data.get("user_dashboard", {})
    except Exception as e:
        pytest.fail(f"[user_dashboard_session] Could not load xpath.toml: {e}")

    login_url = user_xpaths.get("login_url")
    if not login_url:
        pytest.fail("[user_dashboard_session] 'login_url' not found in [user_dashboard] section of xpath.toml")

    credentials = config.get("credentials", {})

    print(f"[user_dashboard_session] Opening User Dashboard in a new tab: {login_url}")
    user_page = page.context.new_page()
    user_page.bring_to_front()
    user_page.goto(login_url, wait_until="load", timeout=90000)
    user_page.screenshot(path=f"screenshots/user_dashboard_landing_{datetime.now().strftime('%H%M%S')}.jpg")

    # Determine whether we need to log in
    try:
        selector = f"({user_xpaths['email_input']}) | ({user_xpaths['new_appointment_btn']})"
        print("[user_dashboard_session] Waiting for login form or dashboard...")
        user_page.locator(selector).first.wait_for(state="visible", timeout=60000)

        if user_page.locator(user_xpaths["new_appointment_btn"]).is_visible():
            print("[user_dashboard_session] Already logged in via shared session.")
        else:
            print("[user_dashboard_session] Login form detected — logging in.")
            user_page.locator(user_xpaths["email_input"]).fill(credentials.get("user_email", ""))
            user_page.locator(user_xpaths["password_input"]).fill(credentials.get("user_password", ""))
            user_page.locator(user_xpaths["login_btn"]).click()
            user_page.wait_for_selector(user_xpaths["new_appointment_btn"], timeout=60000)
            print("[user_dashboard_session] Logged in successfully.")
    except Exception as e:
        user_page.screenshot(path=f"screenshots/user_dashboard_login_error_{datetime.now().strftime('%H%M%S')}.jpg")
        user_page.close()
        pytest.fail(f"[user_dashboard_session] Could not reach User Dashboard: {e}")

    yield user_page, user_xpaths, config

    print("[user_dashboard_session] Closing User Dashboard tab.")
    user_page.close()


# ---------------------------------------------------------------------------
# Employee Portal session — separate persistent context, employee SSO identity
# ---------------------------------------------------------------------------

from contextlib import contextmanager
import json as _json


def _login_employee_in_tab(emp_page, target_url, admin_xpaths, emp_email, emp_password):
    """Drive the SSO + MFA flow on a brand-new tab, explicitly typing the
    employee credentials. Has longer timeouts than the generic
    `_perform_login` because the MS sign-in form can take 10–20s to
    render when there's no cached MS session (which is our case after
    clearing cookies)."""
    print(f"[emp_login] Navigating to {target_url}")
    emp_page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
    emp_page.wait_for_timeout(2000)

    # Wait for the app's SSO button and click it
    print("[emp_login] Waiting for SSO login button on app page...")
    emp_page.wait_for_selector(admin_xpaths["login_with_sso"], timeout=30000)
    emp_page.locator(admin_xpaths["login_with_sso"]).click()
    print("[emp_login] Clicked 'Login with SSO'")

    # Wait for redirect to Microsoft
    emp_page.wait_for_url("**/login.microsoftonline.com/**", timeout=60000)
    emp_page.wait_for_load_state("domcontentloaded")
    print(f"[emp_login] Reached MS login: {emp_page.url[:80]}…")

    # If MS shows an account picker (because of admin's MS session), click
    # "Use another account" so we can type the employee email.
    try:
        use_another = emp_page.locator(
            "xpath=//*[normalize-space()='Use another account' or contains(., 'another account')]"
        ).first
        if use_another.is_visible(timeout=4000):
            print("[emp_login] Clicking 'Use another account'")
            use_another.click()
            emp_page.wait_for_load_state("domcontentloaded")
            emp_page.wait_for_timeout(1500)
    except Exception:
        pass

    # Fill email — longer wait + alternate selectors for resilience
    print(f"[emp_login] Filling email: {emp_email}")
    email_input = None
    for selector in (
        admin_xpaths["email_input"],
        "xpath=//input[@type='email']",
        "xpath=//input[@name='loginfmt']",
    ):
        candidate = emp_page.locator(selector).first
        try:
            candidate.wait_for(state="visible", timeout=20000)
            email_input = candidate
            break
        except Exception:
            continue
    if email_input is None:
        emp_page.screenshot(path=f"screenshots/emp_login_no_email_input_{datetime.now().strftime('%H%M%S')}.jpg")
        raise RuntimeError(f"Could not locate MS email input on {emp_page.url}")
    email_input.fill(emp_email)
    emp_page.locator(admin_xpaths["next_button"]).click()
    emp_page.wait_for_load_state("domcontentloaded")
    emp_page.wait_for_timeout(2000)

    # Fill password
    print("[emp_login] Filling password")
    pw_input = None
    for selector in (
        admin_xpaths["password_input"],
        "xpath=//input[@type='password']",
        "xpath=//input[@name='passwd']",
    ):
        candidate = emp_page.locator(selector).first
        try:
            candidate.wait_for(state="visible", timeout=30000)
            pw_input = candidate
            break
        except Exception:
            continue
    if pw_input is None:
        emp_page.screenshot(path=f"screenshots/emp_login_no_pw_input_{datetime.now().strftime('%H%M%S')}.jpg")
        raise RuntimeError(f"Could not locate MS password input on {emp_page.url}")
    pw_input.fill(emp_password)
    emp_page.locator(admin_xpaths["sign_in_button"]).click()
    emp_page.wait_for_load_state("domcontentloaded")

    # Optional 'Stay signed in?'
    try:
        stay_btn = emp_page.locator(admin_xpaths["stay_signed_in_yes"])
        stay_btn.wait_for(state="visible", timeout=8000)
        print("[emp_login] Clicking 'Stay signed in: Yes'")
        stay_btn.click()
    except Exception:
        pass

    # MFA — user approves on their phone
    print("\n" + "=" * 60)
    print("  *** ACTION REQUIRED: APPROVE MFA ON EMPLOYEE PHONE ***")
    print("  Waiting up to 2 minutes for dashboard…")
    print("=" * 60 + "\n")
    emp_page.wait_for_url("**/dashboard", timeout=120000)
    emp_page.wait_for_selector(admin_xpaths["dashboard_welcome_text"], timeout=30000)
    print("[emp_login] ✓ Employee dashboard reached")


@contextmanager
def employee_tab(admin_page, admin_xpaths, config):
    """Context manager: open a NEW TAB in admin's existing browser context,
    log in as the employee, yield that tab, then restore admin's cookies.

    Use this AFTER admin has finished any seeding work in admin_page — the
    employee login overwrites admin's SSO cookies for the duration of the
    `with` block. On exit, admin's cookies are restored so subsequent
    admin-only tests still work.

    First call requires MFA approval on the employee's phone. Cookies for
    the employee are persisted in `employee_cookies.json` so subsequent
    calls skip MFA (the SSO redirect just reuses the cached MS session).

    Usage:
        admin_page, admin_xpaths, config = admin_session
        # ... admin seeds appointments / assigns to employee here ...
        with employee_tab(admin_page, admin_xpaths, config) as emp_page:
            # emp_page is the new tab, logged in as the employee
            ...
    """
    credentials = config["credentials"]
    target_url = config["admin"]["url"]
    emp_cookies_file = "employee_cookies.json"

    # 1) Snapshot admin's full cookie set so we can restore at the end.
    saved_admin_cookies = admin_page.context.cookies()
    print(f"[employee_tab] Snapshotted {len(saved_admin_cookies)} admin cookies")

    # 2) Try to load cached employee cookies; if present we can skip the
    # full SSO + MFA dance on subsequent runs.
    cached_emp_cookies = None
    if os.path.exists(emp_cookies_file):
        try:
            with open(emp_cookies_file) as f:
                cached_emp_cookies = _json.load(f)
        except Exception:
            cached_emp_cookies = None

    # 3) Swap cookies so the new tab opens AS the employee (or with no
    # session at all if first run).
    admin_page.context.clear_cookies()
    if cached_emp_cookies:
        try:
            admin_page.context.add_cookies(cached_emp_cookies)
            print(f"[employee_tab] Loaded {len(cached_emp_cookies)} cached employee cookies")
        except Exception as e:
            print(f"[employee_tab] Could not apply cached employee cookies: {e}")

    # 4) Open a real second TAB in admin's existing context.
    emp_page = admin_page.context.new_page()
    emp_page.set_default_navigation_timeout(120000)
    emp_page.set_default_timeout(120000)
    emp_page.bring_to_front()

    # 5) Decide path: try to land on /dashboard first (skip SSO if cached),
    # otherwise drive the full SSO + MFA flow with explicit emp credentials.
    try:
        emp_page.goto(
            target_url.rstrip("/") + "/dashboard",
            wait_until="domcontentloaded",
            timeout=20000,
        )
        emp_page.wait_for_timeout(2000)
    except Exception:
        pass

    if "/dashboard" in emp_page.url:
        print("[employee_tab] Cached cookies were valid — skipped SSO")
    else:
        # Full SSO with explicit employee creds + extended waits
        try:
            _login_employee_in_tab(
                emp_page,
                target_url,
                admin_xpaths,
                credentials["employee_email"],
                credentials["employee_password"],
            )
        except Exception as e:
            print(f"[employee_tab] Login attempt failed ({e}); clearing cookies and retrying")
            admin_page.context.clear_cookies()
            _login_employee_in_tab(
                emp_page,
                target_url,
                admin_xpaths,
                credentials["employee_email"],
                credentials["employee_password"],
            )

    # 6) Cache fresh employee cookies for next test
    try:
        new_emp_cookies = emp_page.context.cookies()
        with open(emp_cookies_file, "w") as f:
            _json.dump(new_emp_cookies, f)
        print(f"[employee_tab] Cached {len(new_emp_cookies)} employee cookies for future tests")
    except Exception as e:
        print(f"[employee_tab] Could not cache employee cookies: {e}")

    try:
        yield emp_page
    finally:
        # 7) Teardown: close the tab and restore admin's cookies so the
        # next admin-only test starts on a working session.
        try:
            emp_page.close()
        except Exception:
            pass
        try:
            admin_page.context.clear_cookies()
            admin_page.context.add_cookies(saved_admin_cookies)
            print("[employee_tab] Restored admin cookies — next admin test will see admin identity")
        except Exception as e:
            print(f"[employee_tab] Warning: failed to restore admin cookies: {e}")


# ---------------------------------------------------------------------------
# Login logic (always runs the full login flow)
# ---------------------------------------------------------------------------

def _perform_login(page, target_url, admin_xpaths, credentials):
    """Navigate to the app and run the login flow if needed."""
    
    # Retry loop for initial navigation to handle net::ERR_ABORTED
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"[Login] Navigating to {target_url} (Attempt {attempt+1}/{max_retries})...")
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            break
        except Exception as e:
            print(f"[Login] Navigation attempt {attempt+1} failed: {e}")
            if attempt == max_retries - 1:
                raise e
            page.wait_for_timeout(3000)

    # Step 0: Check if session is already active (try reaching dashboard directly)
    print(f"[Login] Checking session state at {page.url}...")
    if "/dashboard" in page.url:
        print("[Login] Already on dashboard. Skipping login.")
        return
        
    try:
        # If we're at /login, try navigating to /dashboard once to see if it lets us in
        if "/login" in page.url:
            print("[Login] At /login, attempting to jump to /dashboard...")
            page.goto(f"{target_url.rstrip('/')}/dashboard")
            # Wait for either /dashboard (success) or /login (failure/redirect)
            page.wait_for_load_state("networkidle", timeout=10000)
            page.wait_for_timeout(2000)
            
            # Check if we are REALLY on dashboard (not just a redirect param in URL)
            is_on_dashboard = "/dashboard" in page.url and "/login" not in page.url
            
            if is_on_dashboard:
                # Ensure no error message is present
                err_loc = page.locator(f"{admin_xpaths['session_expired_msg']} | {admin_xpaths['network_error_msg']}")
                if err_loc.count() == 0 or not err_loc.first.is_visible(timeout=1000):
                    print("[Login] Session restored via direct navigation. Skipping login.")
                    return
            print(f"[Login] Session not restored (URL: {page.url}). Proceeding to login flow...")
            if "/login" not in page.url:
                page.goto(target_url)
    except Exception as e:
        print(f"[Login] Error during session restoration check: {e}")

    # Ensure we are at the target URL (login page) before starting flow
    if "/dashboard" not in page.url:
        print(f"[Login] Not logged in. Navigating to {target_url}...")
        page.goto(target_url)

    # Step 0.1: Check for session expiration or network error and retry if found
    print(f"[Login] Resilience check (URL: {page.url})...")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)
    
    # Corrected: Use pipe (|) instead of comma for combined XPath
    error_locator = page.locator(f"{admin_xpaths['session_expired_msg']} | {admin_xpaths['network_error_msg']}")
    
    if error_locator.count() > 0 and error_locator.first.is_visible(timeout=5000):
        error_text = error_locator.first.inner_text()
        print(f"[Login] Resilience: Error detected: '{error_text}'. Reloading...")
        page.reload()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

    page.wait_for_load_state("domcontentloaded")

    # Step 0.2: Final check if we are already logged in after navigation/reloads
    if "/dashboard" in page.url and "?" not in page.url:
        print("[Login] Authenticated state confirmed. Skipping SSO click.")
        return

    # Step 1: Wait for the SSO login button and click it
    print("[Login] Waiting for SSO login button...")
    try:
        page.wait_for_selector(admin_xpaths["login_with_sso"], timeout=15000)
        
        # Check for dashboard redirection before clicking
        if "/dashboard" in page.url:
            print("[Login] Redirection detected during SSO wait. Skipping.")
            return

        print("[Login] Clicking 'Login with SSO'...")
        page.locator(admin_xpaths["login_with_sso"]).click()
    except Exception as e:
        if "/dashboard" in page.url:
            print("[Login] Authenticated state confirmed in except block. Proceeding.")
            return
        print(f"[Login] SSO button not found and not on dashboard: {e} — current URL: {page.url}")

    # Step 2: Wait for Microsoft login page
    print("[Login] Waiting for Microsoft login page...")
    try:
        page.wait_for_url("**/login.microsoftonline.com/**", timeout=60000)
        page.wait_for_load_state("networkidle", timeout=60000)
    except Exception as e:
        print(f"[Login] Warning: Microsoft page redirect timed out or URL mismatch: {e}")
        # If we are already on a login page or account picker, continue
        if "microsoftonline.com" not in page.url:
            raise e
    print(f"[Login] On MS page: {page.url}")

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


# ---------------------------------------------------------------------------
# HTML Reporting hooks
# ---------------------------------------------------------------------------

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    Hook to capture screenshot on failure and add it to the HTML report.
    """
    outcome = yield
    report = outcome.get_result()
    extra = getattr(report, "extra", [])

    # Add test description from docstring
    if item.obj.__doc__:
        report.description = item.obj.__doc__.strip()
    else:
        report.description = ""

    if report.when == "call":
        xfail = hasattr(report, "wasxfail")
        if (report.skipped and xfail) or (report.failed and not xfail):
            # Capture screenshot if 'admin_session' fixture is used
            if "admin_session" in item.fixturenames:
                try:
                    page, admin_xpaths, config = item.funcargs["admin_session"]
                    
                    # Screenshots are now stored in the folder 'screenshots'
                    screenshot_dir = "screenshots"
                    if not os.path.exists(screenshot_dir):
                        os.makedirs(screenshot_dir)
                    
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    screenshot_name = f"{item.name}_{timestamp}.jpg"
                    screenshot_path = os.path.join(screenshot_dir, screenshot_name)
                    
                    page.screenshot(path=screenshot_path)
                    if os.path.exists(screenshot_path):
                        from pytest_html import extras
                        # Use relative path for HTML embedding
                        extra.append(extras.image(screenshot_path))
                except Exception as e:
                    print(f"Failed to capture screenshot: {e}")

        report.extra = extra


def pytest_configure(config):
    """
    Ensure report directory exists before tests start.
    """
    screenshot_dir = "screenshots"
    if not os.path.exists(screenshot_dir):
        os.makedirs(screenshot_dir)


# ---------------------------------------------------------------------------
# Deterministic test-file ordering.
# Tests have data dependencies across files: manage_calendar must run first
# (creates the calendars), then book_appointment (books slots on those
# calendars), then manage_appointment (operates on the booked rows). pytest's
# default alphabetical collection puts them in the wrong order, so we re-sort
# items after collection using an explicit precedence list.
# Any file not in the list keeps its default position AFTER the listed ones.
# ---------------------------------------------------------------------------
_FILE_ORDER = (
    "test_manage_calendar.py",
    "test_book_appointment.py",
    "test_manage_appointment.py",
)


def pytest_collection_modifyitems(config, items):
    def order_key(item):
        # nodeid looks like "tests/test_book_appointment.py::test_xxx"
        for idx, name in enumerate(_FILE_ORDER):
            if name in item.nodeid:
                return (idx, item.nodeid)
        return (len(_FILE_ORDER), item.nodeid)  # unknown files run last
    items.sort(key=order_key)

def pytest_html_report_title(report):
    report.title = "Manage Calendar"

def pytest_html_results_table_header(cells):
    cells.insert(2, "<th>Description</th>")
    cells.insert(1, '<th class="sortable time" data-column-type="time">Time</th>')
    cells.pop()

def pytest_html_results_table_row(report, cells):
    cells.insert(2, f"<td>{getattr(report, 'description', '')}</td>")
    cells.insert(1, f'<td class="col-time">{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</td>')
    cells.pop()


# Remove the unused pytest_runtest_protocol hook if it was there
