"""Log in by hand once, then watch one element on a page and ping your phone via ntfy.

Instead of reloading on a timer, a MutationObserver inside the page reports
changes the instant they happen. Use --reload for pages that never update
on their own (you'd normally have to press F5 to see changes).
"""
import argparse
import json
import os
import threading
import time

import requests
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

# Injected into every page load in the watched tab. Mutations are batched
# (250 ms) and Python is only called when the element's text really differs.
OBSERVER_JS = """
(selector) => {
  let last, timer = null, missTimer = null;
  // Elements briefly vanish while a page loads, so only report "missing"
  // if it's still gone after 10 s (e.g. you got logged out).
  const reportMissing = () => {
    missTimer = null;
    if (!document.querySelector(selector)) window.__watchChanged(null);
  };
  const check = () => {
    timer = null;
    const el = document.querySelector(selector);
    if (!el) { missTimer ??= setTimeout(reportMissing, 10000); return; }
    clearTimeout(missTimer); missTimer = null;
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


class Notifier:
    """Sends ntfy pushes on a background thread so the watcher never blocks."""

    def __init__(self, topic, click_url):
        self.endpoint = f"https://ntfy.sh/{topic}"
        self.click_url = click_url
        self.http = requests.Session()  # reuses the connection = faster sends

    def send(self, msg, title="Page changed", priority="urgent"):
        threading.Thread(target=self._send, args=(msg, title, priority), daemon=True).start()

    def _send(self, msg, title, priority):
        headers = {"Title": title, "Priority": priority, "Click": self.click_url}
        for attempt in range(3):
            try:
                self.http.post(self.endpoint, data=msg.encode("utf-8"),
                               headers=headers, timeout=10).raise_for_status()
                return
            except requests.RequestException as e:
                log(f"Notify failed ({e}), retrying...")
                time.sleep(2 ** attempt)
        log("Gave up sending notification.")


def read_text(page, selector):
    return page.evaluate("s => document.querySelector(s)?.innerText.trim() ?? null", selector)


def main():
    args = parse_args()
    notifier = Notifier(args.topic, args.url)
    state = {"armed": False, "last": None, "missing": False}

    def on_change(text):
        # Ignore everything until the user has pressed Enter.
        if not state["armed"]:
            return
        if text is None:
            if not state["missing"]:
                state["missing"] = True
                log("Element missing - logged out?")
                notifier.send(f"Can't find {args.selector} - logged out or page changed?",
                              title="Watcher warning", priority="high")
            return
        state["missing"] = False
        if text == state["last"]:
            return
        state["last"] = text
        log("Change detected")
        notifier.send(text[:300] or "(now empty)")

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
