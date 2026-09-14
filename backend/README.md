# Fraud & Risk Detection Platform — Backend (Database + CRUD APIs)

FastAPI + SQLAlchemy 2.0 + PostgreSQL backend providing the **database setup and CRUD APIs**:
users & roles, customers, transactions, devices, IP addresses, alerts, investigations,
feedback, reports, and audit logs. JWT auth + role-based access + API-key auth for
external integrations.

The database ships **empty** — no demo data. You create your own users via the register API.

## Quick Start

```bash
cd backend
python -m venv venv
venv\Scripts\activate            # Windows  (Linux/Mac: source venv/bin/activate)
pip install -r requirements.txt

# 1. Make sure DATABASE_URL in .env points to your PostgreSQL instance, then:
python init_db.py                # creates all tables (empty)

# 2. Start the API
uvicorn app.main:app --reload --port 8000
```

Interactive docs: http://localhost:8000/docs

### First user

There is no seeded login. Register your first user and use it for everything
(created users can manage others via admin endpoints):

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@yourcompany.com", "password": "YourPassword123", "full_name": "Admin", "role": "admin"}'
```

Then login:

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@yourcompany.com", "password": "YourPassword123"}'
```

The response contains the `access_token` — send it as `Authorization: Bearer <token>`.

### Database management

```bash
python init_db.py          # create all tables (skips existing)
python init_db.py --drop   # drop all tables, then recreate (destructive!)
```

### Reset to an empty database

```bash
python -c "from app.db.session import engine, Base; import app.models; Base.metadata.drop_all(bind=engine)"
python init_db.py
```

### Smoke test (uses a throwaway SQLite DB, never touches your Postgres)

```bash
python smoke_test.py
```

## Roles

| Role | Access |
|---|---|
| `admin` | Everything: user management, API clients, reports, audit logs, deletes |
| `business_manager` | Customers, alerts, reports, CSV import |
| `analyst` | Read APIs, alerts review, investigations, feedback |

## Project Structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI app + router mounting
│   ├── core/
│   │   ├── config.py           # Settings from .env
│   │   ├── security.py         # bcrypt, JWT, API-key hashing
│   │   └── deps.py             # get_current_user, require_roles, get_api_client
│   ├── db/session.py           # engine, SessionLocal, Base, get_db
│   ├── models/                 # SQLAlchemy 2.0 models (12 tables)
│   ├── schemas/                # Pydantic v2 request/response models
│   ├── crud/
│   │   ├── base.py             # generic list/get/create/update/delete
│   │   └── fraud.py            # domain CRUD (profiles, alerts, investigations)
│   ├── api/                    # routers: auth, transactions, fraud, network, dashboard
│   └── utils/datetime.py
├── init_db.py                  # creates all tables (no data)
├── smoke_test.py               # end-to-end API test (SQLite, throwaway)
└── requirements.txt
```

## Database Schema (12 tables)

| Table | Purpose |
|---|---|
| `users` | Admin / Business Manager / Analyst, bcrypt passwords |
| `api_clients` | External businesses, hashed API keys + quota |
| `customers` | Customer profile + transaction aggregates (counts, avg/min/max, velocity) |
| `transactions` | Transactions with customer/device/IP links and status |
| `devices` | Device fingerprints |
| `device_usages` | Customer↔device link table |
| `ip_addresses` | IPs, geo, VPN flag |
| `alerts` | Alerts with status workflow (new/investigating/confirmed_fraud/false_positive/resolved) |
| `investigations` | Analyst case notes |
| `model_feedback` | Analyst feedback (confirmed fraud / false positive) |
| `reports` | Generated report payloads |
| `audit_logs` | Audit trail of sensitive actions |

## API Reference

Auth: `POST /api/auth/register` · `POST /api/auth/login` · `GET /api/auth/me` ·
`GET/PATCH /api/auth/users` (admin) · `POST/GET /api/auth/api-clients` (admin)

Transactions (JWT): `GET /api/transactions` (search, filters, pagination) ·
`GET /api/transactions/{id}` · `GET /api/transactions/{id}/details` (full view with
customer, history, devices, IPs, related txns) · `POST /api/transactions/import/csv`

External API (X-API-Key header): `POST /api/transactions`

Fraud domain: `GET/POST/PATCH/DELETE /api/customers` · `GET/POST /api/alerts` ·
`POST /api/alerts/{id}/review` · `GET/POST /api/investigations` ·
`PATCH /api/investigations/{id}` · `GET/POST /api/feedback` ·
`GET/POST /api/reports` + `GET /api/reports/{id}/export?format=csv|json` ·
`GET /api/audit-logs` (admin)

Dashboard & network: `GET /api/dashboard` (counts, 7-day activity, top customers) ·
`GET /api/network` (customer↔device↔IP graph data)

### Example: submit a transaction externally

First create an API client (admin JWT required):

```bash
curl -X POST http://localhost:8000/api/auth/api-clients \
  -H "Authorization: Bearer <admin-token>" -H "Content-Type: application/json" \
  -d '{"name": "My Store"}'
```

The response contains `api_key` — shown only once. Then:

```bash
curl -X POST http://localhost:8000/api/transactions \
  -H "X-API-Key: <your-key>" -H "Content-Type: application/json" \
  -d '{
    "customer_id": "CUST-1029",
    "amount": 1200.00,
    "payment_method": "card",
    "ip_address": "203.0.113.7",
    "device_id": "device-x",
    "country": "US"
  }'
```

## Security

- bcrypt password hashing, JWT bearer tokens with role claims
- Role-based access on every endpoint (analyst < business_manager < admin)
- Hashed API keys for external integrations (raw key shown only once at creation)
- Audit logging of alert reviews

## Notes

- Alembic is included in requirements for production migrations
  (`alembic init migrations` + point to `app.db.session.Base.metadata`).
- Scoring/ML/rule-engine logic is intentionally excluded — this is the database + CRUD layer only.
