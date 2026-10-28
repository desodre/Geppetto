"""A complete login flow against the small Android app in login_app/."""

from geppetto import By

PACKAGE = "com.example.geppettologindemo"


def test_login(login_app):
    login_app.click(login_app.await_widget(By.ID, f"{PACKAGE}:id/username"))
    login_app.input_text("demo")

    login_app.click(login_app.await_widget(By.ID, f"{PACKAGE}:id/password"))
    login_app.input_text("geppetto", log_text=False)

    login_app.click(login_app.await_widget(By.ID, f"{PACKAGE}:id/login_button"))
    assert login_app.await_widget(By.TEXT, "Welcome, demo!")
