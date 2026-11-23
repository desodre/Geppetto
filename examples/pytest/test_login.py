"""A complete login flow against the small Android app in login_app/."""

from geppetto import By, expect

PACKAGE = "com.example.geppettologindemo"


def test_login(login_app):
    login_app.get(By.ID, f"{PACKAGE}:id/username").fill("demo")
    login_app.get(By.ID, f"{PACKAGE}:id/password").fill("geppetto", log_text=False)
    login_app.get(By.ID, f"{PACKAGE}:id/login_button").click()
    expect(login_app.get(By.TEXT, "Welcome, demo!")).to_be_visible()
