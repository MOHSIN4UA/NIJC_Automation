import pytest
import toml
from playwright.sync_api import Page, expect

@pytest.fixture(scope="session")
def bot_session(playwright):
    """
    Launches browser, navigates to the URL, and yields (page, xpaths).
    """
    config = toml.load("conf.toml")
    xpaths = toml.load("xpath.toml")["xpaths"]
    url = config["app"]["url"]
    
    # Launch browser
    browser = playwright.chromium.launch(
        headless=config["playwright"].get("headless", True)
    )
    
    # Create context and page
    context = browser.new_context(
        viewport=config["playwright"].get("viewport", {"width": 1280, "height": 720})
    )
    page = context.new_page()
    page.goto(url)
    page.wait_for_load_state("networkidle")
    
    yield page, xpaths
    
    # Cleanup
    browser.close()

@pytest.mark.smoke
def test_chatbot_is_visible(bot_session):
    """
    Test that the chatbot launcher is visible.
    """
    page, xpaths = bot_session
    chatbot_launcher = page.locator(xpaths["chatbot_launcher"])
    
    # Wait for the launcher and assert it is visible
    expect(chatbot_launcher).to_be_visible()
    print("Verified: Chatbot launcher is visible.")

@pytest.mark.smoke
@pytest.mark.regression
def test_chatbot_clickable(bot_session):
    """
    Test that the chatbot launcher opens the welcome screen and shows all expected elements.
    """
    page, xpaths = bot_session
    
    # 1. Click Launcher
    chatbot_launcher = page.locator(xpaths["chatbot_launcher"])
    chatbot_launcher.click()
    
    # 2. Wait for welcome screen and verify all its elements
    #page.wait_for_selector(xpaths["carousel_img"])
    expect(page.locator(xpaths["carousel_img"]).first).to_be_visible()
    
    # 3. Verify all 5 language options are visible
    expect(page.locator(xpaths["begin_english"])).to_be_visible()
    expect(page.locator(xpaths["begin_spanish"])).to_be_visible()
    expect(page.locator(xpaths["begin_french"])).to_be_visible()
    expect(page.locator(xpaths["begin_creole"])).to_be_visible()
    expect(page.locator(xpaths["begin_arabic"])).to_be_visible()
    
    # 4. Verify Terms & Conditions footer
    expect(page.locator(xpaths["terms_link"])).to_be_visible()
    
    print("Verified: Welcome screen, carousel image, language options, and footer are visible.")

    
   
