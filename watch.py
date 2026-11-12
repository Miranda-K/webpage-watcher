"""Log in by hand once, then watch one element on a page and ping your phone via ntfy."""
import argparse
import os
import time

import requests
from playwright.sync_api import sync_playwright


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=os.getenv("WATCH_URL", "https://example.com"),
                    help="page to open first")
    ap.add_argument("--selector", default=os.getenv("WATCH_SELECTOR", "body"),
                    help='CSS selector of the part to watch, e.g. "#status"')
    ap.add_argument("--topic", default=os.getenv("NTFY_TOPIC"),
                    help="ntfy topic (or set NTFY_TOPIC)")
    ap.add_argument("--interval", type=float, default=5, help="seconds between checks")
    args = ap.parse_args()
    if not args.topic:
        ap.error("no ntfy topic: pass --topic or set NTFY_TOPIC")
    return args


def log(msg):
    print(time.strftime("[%H:%M:%S]"), msg, flush=True)


def notify(topic, msg):
    requests.post(f"https://ntfy.sh/{topic}", data=msg.encode("utf-8"),
                  headers={"Title": "Page changed", "Priority": "urgent"}, timeout=10)


def read_text(page, selector):
    return page.evaluate("s => document.querySelector(s)?.innerText.trim() ?? null", selector)


def main():
    args = parse_args()
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context("./profile", headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(args.url)

        while True:
            input("Log in, go to the page, then press Enter... ")
            last = read_text(page, args.selector)
            if last is not None:
                break
            print(f"Can't find {args.selector!r} on this page. Fix it and press Enter again.")
        log("Watching. Ctrl+C to stop.")

        while True:
            time.sleep(args.interval)
            try:
                page.reload()
                current = read_text(page, args.selector)
            except Exception as e:
                log(f"Check failed: {e}")
                continue
            if current != last:
                notify(args.topic, current[:300] if current else "(element gone)")
                log("Change detected")
                last = current


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
