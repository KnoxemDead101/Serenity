"""Responsive layout and dark-theme checks in real Chromium."""

import pytest

expect = pytest.importorskip("playwright.sync_api").expect
PHONE = {"width": 390, "height": 844}
DESKTOP = {"width": 1280, "height": 800}
PAGES = ["/", "/accounts", "/finances", "/income", "/setup"]


@pytest.mark.parametrize("path", PAGES)
def test_pages_fit_phone_and_have_working_menu(page, path):
    page.set_viewport_size(PHONE)
    page.goto(f"http://serenity.test{path}")
    expect(page.locator("h1")).to_be_visible()
    assert page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    ) <= 1
    toggle = page.get_by_role("button", name="Menu")
    nav = page.locator("#site-nav")
    expect(toggle).to_be_visible()
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(nav).to_be_hidden()
    toggle.click()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(nav.get_by_role("link", name="Accounts")).to_be_visible()
    page.keyboard.press("Escape")
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(nav).to_be_hidden()


def test_desktop_navigation_and_dark_theme(page):
    page.set_viewport_size(DESKTOP)
    page.goto("http://serenity.test/accounts")
    expect(page.get_by_role("button", name="Menu")).to_be_hidden()
    active = page.locator("#site-nav a.active")
    expect(active).to_have_text("Accounts")
    expect(active).to_have_attribute("aria-current", "page")
    colors = page.evaluate("""() => {
      const root = getComputedStyle(document.documentElement);
      return [root.getPropertyValue("--color-background").trim(),
        root.getPropertyValue("--color-primary").trim(),
        getComputedStyle(document.body).backgroundColor];
    }""")
    assert colors == ["#0a0a0a", "#c9a44c", "rgb(10, 10, 10)"]


def test_income_page_phone_form_and_navigation(page):
    page.set_viewport_size(PHONE)
    page.goto("http://serenity.test/income")
    button = page.get_by_role("button", name="Add income profile")
    expect(button).to_be_visible()
    assert button.bounding_box()["height"] >= 44
    assert page.locator("#site-nav a[href='/income']").is_visible() is False
    page.get_by_role("button", name="Menu").click()
    assert page.locator("#site-nav a[href='/income']").is_visible()