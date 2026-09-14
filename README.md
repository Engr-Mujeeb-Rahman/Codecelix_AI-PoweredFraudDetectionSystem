# Codecelix — AI-Powered Fraud Detection System

Backend for a fraud & risk detection platform: **database schema + CRUD APIs** built with
**FastAPI + SQLAlchemy 2.0 + PostgreSQL**, JWT role-based auth, and API-key access for
external transaction integrations.

> Scope: this is the database + CRUD layer (no ML/risk scoring by design).

## Features

- **12-table PostgreSQL schema** — users, customers, transactions, devices, IPs, alerts,
  investigations, feedback, reports, audit logs
- **Authentication & RBAC** — JWT bearer tokens, 3 roles (`admin`, `business_manager`, `analyst`)
- **External integration API** — `X-API-Key` auth for businesses to submit transactions
- **Transactions** — list/search/filter/paginate, full detail view, CSV import
- **Fraud workflow** — alerts with review status flow, analyst investigations, feedback storage
- **Reports & dashboard** — generated reports with CSV/JSON export, dashboard counters,
  customer↔device↔IP network graph data
- **Audit logs** for sensitive actions

## Repo layout

```
backend/        FastAPI application (see backend/README.md for full API docs)
frontend/       (reserved for the React dashboard)
```

## Quick start

```bash
cd backend
python -m venv venv
venv\Scripts\activate             # Windows (Linux/Mac: source venv/bin/activate)
pip install -r requirements.txt

cp .env.example .env              # then set DATABASE_URL to your PostgreSQL instance
python init_db.py                 # creates all 12 tables (empty database)

uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/docs for the interactive API documentation.

### First user

The database ships empty — register your first admin via the API:

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@yourcompany.com", "password": "YourPassword123", "full_name": "Admin", "role": "admin"}'
```

### Verify everything works

```bash
cd backend && python smoke_test.py   # end-to-end API test on a throwaway SQLite DB
```

## Documentation

Full API reference, schema tables, roles, and examples: [`backend/README.md`](backend/README.md)

## License

MIT
