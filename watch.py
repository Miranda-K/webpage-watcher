"""Log in by hand once, then watch one element on a page and ping your phone via ntfy.

Instead of reloading on a timer, a MutationObserver inside the page reports
changes the instant they happen. Use --reload for pages that never update
on their own (you'd normally have to press F5 to see changes).
"""
import argparse
import json
import os
import time

import requests
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

# Injected into every page load in the watched tab. Mutations are batched
# (250 ms) and Python is only called when the element's text really differs.
OBSERVER_JS = """
(selector) => {
  let last, timer = null;
  const check = () => {
    timer = null;
    const el = document.querySelector(selector);
    if (!el) return;
    const text = el.innerText.trim();
    if (text !== last) { last = text; window.__watchChanged(text); }
  };
  const start = () => {
    new MutationObserver(() => { timer ??= setTimeout(check, 250); })
      .observe(document.documentElement,
               {subtree: true, childList: true, characterData: true});
    check();
  };
  document.readyState === "loading"
    ? document.addEventListener("DOMContentLoaded", start) : start();
}
"""


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=os.getenv("WATCH_URL", "https://example.com"),
                    help="page to open first")
    ap.add_argument("--selector", default=os.getenv("WATCH_SELECTOR", "body"),
                    help='CSS selector of the part to watch, e.g. "#status"')
    ap.add_argument("--topic", default=os.getenv("NTFY_TOPIC"),
                    help="ntfy topic (or set NTFY_TOPIC)")
    ap.add_argument("--reload", type=float, default=0, metavar="SECONDS",
                    help="also reload the page every N seconds (0 = never)")
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
    state = {"armed": False, "last": None}

    def on_change(text):
        # Ignore everything until the user has pressed Enter.
        if not state["armed"] or text == state["last"]:
            return
        state["last"] = text
        log("Change detected")
        notify(args.topic, text[:300] or "(now empty)")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context("./profile", headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.expose_function("__watchChanged", on_change)
        page.add_init_script(f"({OBSERVER_JS})({json.dumps(args.selector)})")
        page.goto(args.url)

        while True:
            input("Log in, go to the page, then press Enter... ")
            baseline = read_text(page, args.selector)
            if baseline is not None:
                break
            print(f"Can't find {args.selector!r} on this page. Fix it and press Enter again.")
        state.update(armed=True, last=baseline)
        log("Watching. Ctrl+C to stop.")

        # wait_for_timeout keeps Playwright processing callbacks from the page.
        step = args.reload * 1000 if args.reload else 60_000
        while True:
            page.wait_for_timeout(step)
            if args.reload:
                try:
                    page.reload(wait_until="domcontentloaded")
                except PlaywrightError as e:
                    log(f"Reload failed: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
