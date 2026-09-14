# AgriDirect — SIH Project

## 1. Project Overview

**AgriDirect** is a farmer-to-consumer digital marketplace prototype developed as an **SIH (Smart India Hackathon) project** concept.

The platform is designed to reduce unnecessary intermediaries between farmers and consumers by giving farmers a simple way to publish their produce, manage available stock, receive orders, and use demand-based market intelligence. Consumers can discover produce, compare listings, add items to a basket, place orders, make demo payments, and track their purchases.

The current repository is a working **Flask + SQLite web prototype** implementing the core marketplace and market-intelligence workflow.

---

## 2. Problem the Project Addresses

Farmers can face difficulty in:

- Reaching consumers directly.
- Finding a simple digital channel to sell fresh produce.
- Understanding demand for their crops from available sales information.
- Deciding how much produce to keep available or plan for a future harvest.
- Managing orders and stock after listing produce.

Consumers can face difficulty in:

- Finding locally listed agricultural produce in one place.
- Discovering individual farmer listings.
- Managing purchases and order information through a single interface.

**AgriDirect** addresses these gaps through one role-based platform for **farmers and consumers**.

---

## 3. Proposed Solution

AgriDirect provides two connected workspaces:

### Farmer
Farmers can:
- Create a farmer account and sign in securely.
- Add, edit, and delete produce listings.
- Update available stock.
- View incoming orders and update order status.
- View earnings and recent order information.
- Use the **Smart Price Advisor** to get a suggested price range using AgriDirect sales history, demand trend, and stock level.
- Create **Future Harvest** plans.
- Compare planned harvest with observed demand.
- View **Supply & Demand** information by category.
- Receive farmer-side alerts and notifications.

### Consumer
Consumers can:
- Create a consumer account and sign in.
- Browse available produce.
- Search and filter produce by category.
- Open individual product pages.
- Add/remove products from a wishlist.
- Add products to a basket and change quantities.
- Checkout using the supported demo payment flow or Cash on Delivery.
- View order history and order status.
- Submit and update product reviews.
- Receive notifications.
- Use the available voice-chat interface.

---

## 4. Key SIH-Relevant Features

### Direct Farmer-to-Consumer Marketplace
The core workflow connects farmer listings directly with consumers through a single web application.

### Smart Price Advisor
The application calculates a suggested price from:
- Historical AgriDirect sales for the farmer/product/category.
- Recent vs previous 30-day demand.
- Demand trend: **Rising, Stable, or Softening**.
- Current stock level.

It also provides a suggested price range and explains the data source used.

> This is an application-level intelligence feature based on the project's own transaction data; it is not a live government/mandi market-price feed.

### Future Harvest Intelligence
Farmers can enter a planned future harvest. The system compares the planned quantity plus current stock against estimated demand and reports conditions such as:
- **Potential shortage**
- **Well matched**
- **Possible surplus**
- **Need more sales data**

### Supply & Demand Matching
The farmer dashboard can show category-level supply against recent/projected demand and classify the market as:
- Shortage
- Balanced
- Surplus
- No clear demand

### Multilingual UI
The frontend includes language support for:
- English
- Tamil
- Hindi

### Role-Based Access
The application separates Farmer and Consumer workflows and prevents a logged-in user from accessing the other role's protected dashboard.

### Order and Payment Workflow
The prototype supports:
- Basket/cart management.
- Checkout.
- Cash on Delivery.
- Demo payment success/failure flow.
- Order status progression.
- Payment retry for failed demo payments.

### Wishlist and Reviews
Consumers can save products to a wishlist and submit/update ratings and comments for products.

---

## 5. Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask |
| Database | SQLite |
| Frontend | HTML, CSS, JavaScript |
| Templates | Jinja2 |
| Authentication | Flask sessions + Werkzeug password hashing |
| Internationalization | Custom JavaScript i18n |
| Testing | Flask test client / Python smoke test |

No external database server is required for the current prototype.

---

## 6. Project Structure

```text
AgriDirect_step16_BugFixed/
├── app.py                    # Flask application, routes and business logic
├── agridirect.db             # SQLite database
├── requirements.txt          # Python dependencies
├── test_smoke.py             # Basic application smoke tests
├── README.md                 # Project documentation
├── static/
│   ├── style.css             # Application styling
│   ├── i18n.js               # Language/i18n support
│   └── voice.js              # Voice interface functionality
└── templates/
    ├── role_login.html       # Farmer/Consumer role selection
    ├── login.html            # Role-specific login
    ├── signup.html           # Account creation
    ├── farmer.html           # Farmer dashboard
    ├── consumer.html         # Consumer marketplace
    ├── add_produce.html      # Add produce
    ├── edit_produce.html     # Edit produce
    ├── product.html          # Product details/reviews
    ├── cart.html             # Basket
    ├── checkout.html         # Checkout
    ├── payment.html          # Demo payment
    ├── orders.html            # Order management/history
    ├── future_harvest.html   # Future harvest planning
    ├── supply_demand.html    # Supply/demand intelligence
    ├── wishlist.html         # Consumer wishlist
    └── notifications.html    # Notifications/messages
```

---

## 7. Database Design

The SQLite database contains tables for the main application entities:

- `users` — farmer and consumer accounts.
- `products` — farmer produce listings.
- `orders` — consumer orders.
- `order_items` — products and quantities inside orders.
- `notifications` — user notifications.
- `future_harvests` — farmer harvest plans.
- `wishlist` — saved consumer products.
- `reviews` — consumer ratings and comments.
- `payments` — prototype payment records.

The database schema is automatically created by `app.py` when the application starts.

---

## 8. How to Run the Project

### Requirements

- Python **3.9+**
- pip

### Setup

```bash
python3 -m venv .venv
```

Activate the virtual environment:

**Linux/macOS**
```bash
source .venv/bin/activate
```

**Windows**
```powershell
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the application:

```bash
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

The home page lets the user choose **I'm a Farmer** or **I'm a Consumer**.

---

## 9. Demo Accounts

The included database provides demo credentials for testing:

| Role | Email | Password |
|---|---|---|
| Farmer | `farmer@agridirect.com` | `farmer123` |
| Consumer | `consumer@agridirect.com` | `consumer123` |

Additional accounts can be created from the signup pages.

---

## 10. Testing

Run the included smoke test:

```bash
python test_smoke.py
```

The test verifies important Farmer and Consumer flows, including authentication, protected dashboards, supply/demand and future-harvest pages, wishlist, product access, and a basic checkout flow.

The smoke test temporarily backs up the SQLite database and restores it after execution.

---

## 11. Payment Disclaimer

Payment functionality in this version is a **prototype/demo flow**.

It does **not** process real online payments and does not collect or store real:
- Card numbers
- CVV
- UPI PINs
- Bank credentials

For an SIH production deployment, a certified payment gateway and appropriate security/compliance controls would need to be integrated.

---

## 12. Current Prototype Limitations

This repository is a functional prototype rather than a production deployment. In particular:

- Market intelligence is calculated from data available inside AgriDirect rather than a live external mandi/market-price API.
- The payment gateway is simulated.
- The SQLite database is intended for prototype/local use.
- The current demand model is rule-based and uses recent transaction history.
- Production deployment would require stronger secret management, HTTPS, database hardening, monitoring, and additional security controls.

---

## 13. Future Scope

The platform can be extended with:

1. **Live agricultural market-price integration** from trusted government/market data sources.
2. **AI/ML-based demand forecasting** using larger historical datasets, seasonality, location, crop and price trends.
3. **Farmer location and logistics support** for delivery-radius and route planning.
4. **Real payment-gateway integration**.
5. **Government scheme and agricultural advisory integration**.
6. **Mobile application/PWA support** for easier farmer access.
7. **Stronger multilingual voice interaction** for regional-language users.
8. **Scalable cloud database and deployment** for real-world usage.
9. **Analytics dashboards** for crop demand, pricing and sales trends.

---

## 14. SIH Presentation Summary

**Problem:** Farmers need better direct market access and practical information for selling and planning agricultural produce.

**Solution:** AgriDirect provides a farmer-to-consumer marketplace combined with stock management, order management, demand intelligence, smart pricing and future-harvest planning.

**Innovation:** Instead of being only an online produce store, the prototype uses its transaction history to provide actionable signals about price, demand, supply and future harvest planning.

**Impact:** The proposed system aims to improve farmer market access, support more informed production decisions, and make fresh-produce purchasing simpler for consumers.

---

## 15. Project Status

**Current status:** Working web prototype / SIH demonstration build.

The repository contains the implemented application, database, frontend templates, static assets and smoke tests required to demonstrate the main AgriDirect workflow.
