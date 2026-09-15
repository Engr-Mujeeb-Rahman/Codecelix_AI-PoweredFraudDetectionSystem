# Codecelix Backend — AI Fraud & Risk Detection Platform

Enterprise FastAPI + SQLAlchemy 2.0 + PostgreSQL backend providing:
1. **Database & Schema**: 15 tables on PostgreSQL (Supabase) with native binary `JSONB` for rules and risk assessments.
2. **AI Risk Scoring Engine**: Real-time multi-factor scoring (0–100) combining ML Anomaly Detection + Configurable Rules + Customer Behavior into an automated decision (`APPROVE`, `REVIEW`, `BLOCK`).
3. **ML Anomaly Detection**: Statistical Z-scores for cold-start (<50 txns) and Scikit-Learn `IsolationForest` on historical feature vectors with a live retraining loop.
4. **Fraud Pattern Detectors**: 6 specialized algorithms (velocity, device sharing, IP clustering, location anomalies, impossible travel, behavior shifts).
5. **Configurable Rules Engine**: AST condition-tree evaluator supporting composite `AND`/`OR` rules with admin CRUD and immediate score impacts.
6. **Dual-Mode AI Explanations**: Sub-5ms deterministic bullet points returned synchronously + asynchronous **Google Gemini 2.5 Flash** summary enrichment post-response.
7. **AI Investigation Assistant**: Natural language analyst Q&A powered by Gemini and grounded in real database context (`POST /api/assistant/query`).
8. **Unified Investigation View**: Single-item case view (`GET /api/investigations/{id}`) joining transactions, risk assessments, customer history, and related alerts.
9. **Dynamic Customer Risk Profiles**: Dedicated reader (`GET /api/customers/{id}/risk-profile`) maintaining rolling scores, device counts, and location counts.
10. **Security & RBAC**: JWT bearer tokens with 3 distinct roles (`admin`, `business_manager`, `analyst`) and hashed merchant API keys (`X-API-Key`).

---

## Quick Start

```bash
cd backend
python -m venv venv
venv\Scripts\activate            # Windows (Linux/Mac: source venv/bin/activate)
pip install -r requirements.txt

# 1. Ensure backend/.env contains your DATABASE_URL and GEMINI_API_KEY
python init_db.py                # provisions all 15 tables and seeds default fraud rules

# 2. Start the API
uvicorn app.main:app --reload --port 8000
```

* Interactive Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
* ReDoc UI: [http://localhost:8000/redoc](http://localhost:8000/redoc)
* Health probe: [http://localhost:8000/health](http://localhost:8000/health)

---

## Testing & Verification

### 1. AI Layer End-to-End Test Suite (16 Test Cases)
Verifies rules evaluation, 6 pattern detectors, ML scoring, Gemini explanations, investigations risk linkage, customer risk profiles, and assistant Q&A on an isolated SQLite database:

```bash
python test_ai_layer.py
```

### 2. Pre-Existing CRUD & Auth Regression Suite (18 Test Cases)
Verifies authentication, RBAC permissions, transaction detail views, CSV ingestion, alerts, and customer profile aggregate recomputation:

```bash
python smoke_test.py
```

---

## Database Schema (15 Tables on PostgreSQL)

All tables use UUID primary keys and UTC timestamps. Tables with JSON structures use native PostgreSQL binary `JSONB`:

| Table | Type | Purpose |
|---|---|---|
| `users` | Core | Internal platform users (`admin`, `business_manager`, `analyst`), bcrypt hashed passwords. |
| `api_clients` | Core | External merchants, hashed API keys (`X-API-Key`), usage counters. |
| `customers` | Core | Customer profiles + aggregates (`avg_amount`, `suspicious_transactions`, velocity counters). |
| `transactions` | Core | Financial transaction records with customer, device, IP, and status links. |
| `devices` | Core | Hardware device fingerprints and first-seen timestamps. |
| `device_usages` | Core | Link table mapping customers to devices with usage frequency. |
| `ip_addresses` | Core | IP records with geo-location (country, city) and VPN flags. |
| `alerts` | Core | Fraud alerts with status workflow (`new`, `investigating`, `confirmed_fraud`, `false_positive`, `resolved`). |
| `investigations` | Core | Analyst case files with notes and resolution conclusions. |
| `model_feedback` | Core | Analyst review records feeding the ML retraining loop. |
| `reports` | Core | Generated daily/monthly fraud activity reports. |
| `audit_logs` | Core | Tamper-evident audit trail for sensitive actions. |
| `fraud_rules` | **AI/Risk** | Admin fraud rules with native `JSONB` condition trees and score impacts. |
| `risk_assessments` | **AI/Risk** | Full risk evaluation breakdown with native `JSONB` triggered rules and pattern logs. |
| `customer_risk_profiles`| **AI/Risk** | Dynamic rolling customer risk scores, levels, device counts, and location counts. |

---

## Role-Based Access Control (RBAC)

| Role | Permissions |
|---|---|
| `admin` | Full platform access: user management, merchant API keys, rule creation/deletion, model retraining, report exports, audit logs. |
| `business_manager` | Dashboard, transaction management (manual entry, CSV import), customer views, network graph, report generation. |
| `analyst` | Read-only transactions, alert review & status updates, investigation workspace & notes, AI Investigation Assistant, network graph. |

---

## API Reference

### 1. Authentication & Users
* `POST /api/auth/register` — Register a new user (`admin`, `business_manager`, `analyst`).
* `POST /api/auth/login` — Authenticate and receive a JWT Bearer access token.
* `GET /api/auth/me` — Current user profile.
* `GET /api/auth/users` — List platform users (Admin only).
* `POST /api/auth/api-clients` — Generate a merchant `X-API-Key` (Admin only).

### 2. Real-Time Risk Scoring
* `POST /api/risk-check` — **Synchronous Pre-Flight Scoring**: Evaluates a transaction in sub-5ms without writing to the database. Returns risk score, decision (`APPROVE`/`REVIEW`/`BLOCK`), triggered rules, and explanation.
* `GET /api/risk/{txn_id}` — Retrieves the persisted `RiskAssessment` record and explanation for a stored transaction.
* `POST /api/risk/retrain` — Triggers live retraining of the `IsolationForest` anomaly model on updated historical feature vectors (Admin only).
* `GET /api/risk-metrics` — Retrieves model precision, recall, and feedback counts.

### 3. Transaction Management
* `POST /api/transactions` — External merchant transaction submission via `X-API-Key` header with automatic risk scoring and alert generation.
* `POST /api/transactions/manual` — Internal dashboard manual entry with auto-scoring (Admin / Business Manager).
* `POST /api/transactions/import/csv` — Drag-and-drop CSV batch transaction upload with automated risk scoring.
* `GET /api/transactions` — Paginated transaction listing with multi-field search and filters (status, amount range, date range, customer).
* `GET /api/transactions/{id}` — Single transaction record.
* `GET /api/transactions/{id}/details` — Complete transaction view with linked customer profile, 20-transaction history, associated devices, and IPs.

### 4. Fraud Rules Engine
* `GET /api/rules` — List all active fraud rules and condition trees.
* `POST /api/rules` — Create a new fraud rule with condition tree and score impact (Admin only).
* `GET /api/rules/{id}` — Retrieve rule details.
* `PATCH /api/rules/{id}` — Update rule status (`is_active`), score impact, or conditions (Admin only).
* `DELETE /api/rules/{id}` — Delete a fraud rule (Admin only).

### 5. Investigations & Case Review
* `GET /api/investigations` — List open and closed investigation cases.
* `POST /api/investigations` — Open an investigation case for a transaction.
* `GET /api/investigations/{id}` — **Full Risk-Linked Detail View**: Returns investigation metadata, linked `RiskAssessment` (or `None` if unscored), customer recent transaction history, and related alerts.
* `PATCH /api/investigations/{id}` — Update analyst notes, case conclusion, or close case.

### 6. Customer Risk Profiles
* `GET /api/customers/{id}/risk-profile` — Dedicated reader returning dynamic risk scores, risk levels, unique devices used, and unique locations used (returns 404 if customer is unscored).
* `GET /api/customers` — Paginated customer directory with aggregate counters.
* `GET /api/customers/{id}` — Single customer identity profile.

### 7. AI Investigation Assistant
* `POST /api/assistant/query` — Natural language Q&A endpoint powered by Google Gemini 2.5 Flash with database RAG context.
  * Supports contextual inquiries regarding customer risk, device clusters, and case summaries.

### 8. Fraud Alerts & Network Graph
* `GET /api/alerts` — List alerts with status and severity filters.
* `POST /api/alerts/{id}/review` — Review alert status (`confirmed_fraud` / `false_positive`) and record analyst feedback for model improvement.
* `GET /api/network` — Returns graph nodes (`customers`, `devices`, `ips`) and link edges for network visualization.
* `GET /api/dashboard` — Aggregated KPI metrics, risk distributions, and 7-day trend activity.

---

## Environment Variables

Configured in `backend/.env`:

```env
# PostgreSQL connection string (Supabase)
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/<dbname>

# JWT Security
SECRET_KEY=your-production-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# CORS Whitelist (comma-separated origins)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# Google Gemini API Key for LLM explanations and AI Assistant
GEMINI_API_KEY=your-gemini-api-key
```
