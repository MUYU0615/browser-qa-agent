from app.services.browser import screenshot_filename


def test_screenshot_filename_includes_attempt_number() -> None:
    assert screenshot_filename(1, 2) == "attempt-1-step-2.png"
    assert screenshot_filename(2, 1) == "attempt-2-step-1.png"
