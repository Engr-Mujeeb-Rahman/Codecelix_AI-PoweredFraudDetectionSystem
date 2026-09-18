# Codecelix Backend — AI Fraud & Risk Detection Platform

Enterprise FastAPI + SQLAlchemy 2.0 + PostgreSQL backend providing:
1. **Database & Schema**: 15 tables on PostgreSQL (Supabase) with native binary `JSONB` for rules, triggered events, and risk assessments.
2. **AI Risk Scoring Engine**: Real-time multi-factor scoring (0–100) combining **45% ML Anomaly Detection + 35% Configurable Rules + 20% Customer Behavior** into an automated decision (`APPROVE`, `REVIEW`, `BLOCK`).
3. **Hybrid ML Anomaly Detection**: Primary pipeline `synthetic_fraud_pipeline.joblib` combining **75% supervised XGBoost + 25% unsupervised Isolation Forest** evaluated over 43 features with piecewise calibration (`0–30` Low, `31–70` Medium, `71–100` High) matching `report.txt`.
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

The backend includes a comprehensive **Software Testing Pyramid** covering unit components, whitebox logic, blackbox REST contracts, and full regression suites.

### 1. Consolidated Master Test Runner
Runs all 5 test suites sequentially and outputs an executive quality audit report:

```bash
python run_all_tests.py
```

**Consolidated Test Report:**
```text
===========================================================================
                      CONSOLIDATED TEST AUDIT REPORT
===========================================================================
Test Suite                                    | Duration   | Status
---------------------------------------------------------------------------
1. Component-Level (Unit) Suite               | 16.03s     | [PASS] PASSED
2. Whitebox (Internal Logic) Suite            | 13.67s     | [PASS] PASSED
3. Blackbox (REST API & RBAC) Suite           | 26.15s     | [PASS] PASSED
4. Regression Suite (CRUD & Auth Smoke Test)  | 17.82s     | [PASS] PASSED
5. Regression Suite (AI Layer E2E Test)       | 26.53s     | [PASS] PASSED
---------------------------------------------------------------------------
Total Execution Time                          | 100.19s
===========================================================================

[SUCCESS] ALL TEST SUITES PASSED WITH 100% SUCCESS RATE!
```

### 2. Pytest Test Suites
```bash
# Tier 1: Component-Level Unit Tests (43D features, ML hybrid pipeline, 6 pattern detectors, AST, crypto)
pytest tests/test_components_unit.py -v

# Tier 2: Whitebox Logic Tests (scoring formula weights, critical overrides, DB side effects, customer profiles)
pytest tests/test_whitebox_paths.py -v

# Tier 3: Blackbox REST API Tests (HTTP status codes, RBAC permissions, CSV import, cases, graph analytics)
pytest tests/test_blackbox_api.py -v
```

### 3. Regression Suites
```bash
# Tier 4a: CRUD & Auth Regression Suite (18 checks)
python smoke_test.py

# Tier 4b: End-to-End AI & Risk Intelligence Suite (16 checks)
python test_ai_layer.py
```

---

## Machine Learning Pipelines (`backend/app/ml/artifacts/`)

| File | Architecture | Features | Role |
|:---|:---|:---|:---|
| **`synthetic_fraud_pipeline.joblib`** | **Hybrid Ensemble** (75% XGBoost + 25% Isolation Forest) | 43 raw transactional + 1 anomaly score = 44 features | **Primary Production Model** powering `/api/risk-check` and `/api/transactions` |
| **`ulb_hybrid_fraud_pipeline.joblib`** | Hybrid Credit-Card PCA Pipeline | 37 features (`V1`–`V28`, Amount, Time) | Benchmark model for credit card PCA datasets |
| **`final_fraud_pipeline.pkl`** | IEEE-CIS Pipeline | 75 features (`card1`–`card6`, `C1`–`C14`, `D1`–`D15`, `id_01`–`id_20`) | Benchmark model for e-commerce identity datasets |
| **`report.txt`** | Canonical Thresholds | Decision tiers: `0–30` Low, `31–70` Medium, `71–100` High | Operational decision matrix |
| **`Old/`** | Archived Baseline | 10-feature interim model | Preserved for rollback safety |

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
* `GET /api/risk/{transaction_id}` — Retrieves the stored risk assessment, AI explanation, and raw feature snapshot.
* `GET /api/risk-metrics` — Retrieves model performance indicators (active model status, precision, recall, review breakdown).
* `POST /api/risk/retrain` — Triggers automated background model retraining using analyst-labeled feedback (Admin only).

### 3. Transactions
* `POST /api/transactions` — Merchant transaction ingestion via `X-API-Key`.
* `POST /api/transactions/manual` — Internal dashboard manual entry (Admin / Business Manager).
* `POST /api/transactions/import/csv` — Bulk CSV import with batch scoring (Admin / Business Manager).
* `GET /api/transactions` — Paginated list with filtering and search.
* `GET /api/transactions/{id}/details` — Complete 360-degree transaction view (customer history, linked devices, IPs, related transactions).

### 4. Rules Engine
* `GET /api/rules` — List all active fraud rules and condition trees.
* `POST /api/rules` — Create a new rule (Admin only).
* `PATCH /api/rules/{id}` — Update conditions, status, or score impact.
* `DELETE /api/rules/{id}` — Delete rule (Admin only).

### 5. Investigations & Alerts
* `GET /api/alerts` — List alerts with status and severity filters.
* `POST /api/alerts/{id}/review` — Review alert (`confirmed_fraud`, `false_positive`, `resolved`).
* `GET /api/investigations` — List active and historical case investigations.
* `POST /api/investigations` — Open a case investigation.
* `GET /api/investigations/{id}` — **Unified Investigation Detail View** joining risk assessment, customer history, and related alerts.
* `PATCH /api/investigations/{id}` — Update investigation notes and conclusions.

### 6. Customer Risk Profiles & Assistant
* `GET /api/customers/{id}/risk-profile` — Dynamic customer risk metrics and level.
* `POST /api/assistant/query` — Grounded natural language investigation assistant powered by Google Gemini 2.5 Flash.
* `GET /api/network` — Graph dataset linking Customers, Devices, and IP addresses.
* `GET /api/dashboard` — Platform overview KPIs, alerts breakdown, and risk distribution.
