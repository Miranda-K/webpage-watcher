# webpage-watcher

Log in to a site by hand, then leave your computer. When one part of the page changes, you get a push notification on your phone through [ntfy](https://ntfy.sh).

A `MutationObserver` inside the page reports changes as they happen, about 0.25 s later, with no polling or reloading needed.

## Setup (once)

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

On your phone, install the ntfy app and subscribe to a topic. Use a long random name, because anyone who knows the topic can read it.

## Run

```powershell
$env:NTFY_TOPIC = "your-long-random-topic"
python watch.py --url https://site.com/page --selector "#status"
```

QUICKSTART: `.\start.local.ps1
`

1. A Chrome window opens. Log in and go to the page you want to watch.
2. Press Enter in the terminal. The watcher starts.
3. Leave it running. Don't close the browser window or the laptop lid.

Your login is saved in `%LOCALAPPDATA%\webpage-watcher\profile`, so next time you may only need to press Enter.

## Options

| flag | what it does |
|---|---|
| `--selector` | CSS selector to watch. Right-click the element, choose Inspect, and copy its `#id` or `.class`. If you use `body`, any change on the page triggers an alert. |
| `--reload N` | Also reload every N seconds. Use this for pages that only update when you press F5. |
| `--headless` | Hide the browser window. Only works once your saved login works. |

## Notifications

- **Page changed** (urgent): includes the new text, and tapping it opens the page.
- **Watcher warning** (high): the element has been missing for 10 s. You were probably logged out.

To get alerts during Focus or Do Not Disturb, allow ntfy to bypass them in your phone's settings.
