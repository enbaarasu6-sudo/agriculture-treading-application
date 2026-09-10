# AgriDirect – Easy Farmer / Consumer Login

AgriDirect is a runnable Flask + SQLite farm-to-home marketplace prototype. This version keeps the existing marketplace, farmer dashboard, produce management, orders, wishlist, notifications, checkout, and market intelligence features, while making account identification clearer.

## What changed

- The home page now starts with two clearly labeled cards: **I'm a Farmer** and **I'm a Consumer**.
- Each card explains the correct workspace and has its own sign-in and account-creation action.
- The sign-in screen shows the active role in the badge, heading, artwork, and button.
- A visible **Switch to Farmer / Switch to Consumer** link prevents users from getting stuck in the wrong login.
- The layout is responsive for desktop and mobile screens.

## Run locally

Requires Python 3.9+.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000** in a browser and choose an account type.

The included SQLite database is `agridirect.db`. To start with a fresh database, stop the app and remove that file; the app recreates the schema on the next run.

## Demo accounts

The included database contains these demo accounts:

| Account type | Email | Password |
|---|---|---|
| Farmer | `farmer@agridirect.com` | `farmer123` |
| Consumer | `consumer@agridirect.com` | `consumer123` |

You can also create additional accounts from the role chooser.

## Smoke test

```bash
python test_smoke.py
```

The smoke test makes a temporary database backup and restores the original demo data when it finishes.

## Payment note

Online payment methods in this prototype use a mock/demo gateway. The app does not collect or store real card numbers, CVV, UPI PINs, or bank credentials.
