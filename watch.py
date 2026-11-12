"""Log in by hand once, then watch one element on a page and ping your phone via ntfy."""
import time

import requests
from playwright.sync_api import sync_playwright

URL = "https://example.com"
SELECTOR = "body"
TOPIC = "my-secret-topic-change-me"
INTERVAL = 5


def notify(msg):
    requests.post(f"https://ntfy.sh/{TOPIC}", data=msg.encode("utf-8"),
                  headers={"Title": "Page changed", "Priority": "urgent"}, timeout=10)


with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context("./profile", headless=False)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(URL)

    input("Log in, go to the page, then press Enter... ")
    last = page.inner_text(SELECTOR)
    print("Watching. Ctrl+C to stop.")

    while True:
        time.sleep(INTERVAL)
        try:
            page.reload()
            current = page.inner_text(SELECTOR)
        except Exception as e:
            print("Check failed:", e)
            continue
        if current != last:
            notify("Page changed")
            print("Change detected")
            last = current
