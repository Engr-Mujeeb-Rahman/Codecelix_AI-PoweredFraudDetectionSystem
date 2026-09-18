"""Blackbox REST API & Integration Tests.

Validates the public HTTP REST API surface from the external perspective:
HTTP status codes, RBAC enforcement, input validations, security headers,
and cross-endpoint customer/transaction/investigation lifecycles.
"""
import io
from uuid import uuid4
import pytest


# ============================================================================
# 1. AUTHENTICATION & RBAC PERMISSIONS
# ============================================================================

def test_auth_login_success_and_failure(client):
    """Verifies login with valid vs invalid credentials."""
    # Valid login
    r = client.post("/api/auth/login", json={"email": "admin@testsuite.io", "password": "Passw0rd123!"})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Invalid password
    r_bad = client.post("/api/auth/login", json={"email": "admin@testsuite.io", "password": "WrongPassword!"})
    assert r_bad.status_code == 401

    # Non-existent email
    r_none = client.post("/api/auth/login", json={"email": "ghost@testsuite.io", "password": "Passw0rd123!"})
    assert r_none.status_code == 401


def test_rbac_admin_vs_analyst_permissions(client, admin_headers, analyst_headers):
    """Verifies role-based access control across admin and analyst roles."""
    rule_payload = {
        "name": "RBAC Test Rule",
        "description": "Rule to test RBAC enforcement",
        "rule_type": "threshold",
        "conditions": {"field": "amount", "op": ">", "value": 50000.0},
        "action": "flag_review",
        "score_impact": 20.0,
        "severity": "medium",
    }

    # Admin CAN create rules
    r_admin = client.post("/api/rules", json=rule_payload, headers=admin_headers)
    assert r_admin.status_code == 201

    # Analyst CANNOT create rules (HTTP 403 Forbidden)
    r_analyst = client.post("/api/rules", json=rule_payload, headers=analyst_headers)
    assert r_analyst.status_code == 403

    # Unauthenticated request (HTTP 401 Unauthorized)
    r_unauth = client.post("/api/rules", json=rule_payload)
    assert r_unauth.status_code == 401


# ============================================================================
# 2. REAL-TIME RISK SCORING APIS
# ============================================================================

def test_real_time_risk_check_low_risk(client, merchant_headers):
    """Verifies /api/risk-check scores legitimate transaction as LOW / APPROVE."""
    payload = {
        "customer_id": "CUST-BB-001",
        "amount": 45.0,
        "currency": "USD",
        "payment_method": "card",
        "country": "US",
        "city": "New York",
    }
    r = client.post("/api/risk-check", json=payload, headers=merchant_headers)
    assert r.status_code == 200
    res = r.json()
    assert res["risk_score"] <= 30.0
    assert res["risk_level"] == "LOW"
    assert res["decision"] == "APPROVE"
    assert "explanation" in res


def test_real_time_risk_check_high_risk_anomaly(client, merchant_headers):
    """Verifies /api/risk-check scores multi-factor fraud simulation as HIGH / BLOCK."""
    payload = {
        "customer_id": "CUST-BB-002",
        "amount": 9500.0,
        "currency": "USD",
        "payment_method": "crypto",
        "country": "RU",
        "city": "Moscow",
        "ip_address": "185.220.101.5",
        "device_id": "UNSEEN-FRAUD-DEV-999",
    }
    r = client.post("/api/risk-check", json=payload, headers=merchant_headers)
    assert r.status_code == 200
    res = r.json()
    assert res["risk_score"] >= 70.0
    assert res["risk_level"] == "HIGH"
    assert res["decision"] in ("BLOCK", "REVIEW")


def test_risk_metrics_and_retraining_endpoints(client, admin_headers, analyst_headers):
    """Verifies /api/risk-metrics inspection and admin-only /api/risk/retrain."""
    # Metrics viewable by authenticated users
    r = client.get("/api/risk-metrics", headers=analyst_headers)
    assert r.status_code == 200
    metrics = r.json()
    assert "model_status" in metrics
    assert "Hybrid XGBoost + Isolation Forest" in metrics["model_status"]

    # Retrain accessible by admin
    r_retrain = client.post("/api/risk/retrain", headers=admin_headers)
    assert r_retrain.status_code == 200
    assert "success" in r_retrain.json()

    # Retrain blocked for analyst
    r_block = client.post("/api/risk/retrain", headers=analyst_headers)
    assert r_block.status_code == 403


# ============================================================================
# 3. TRANSACTION INGESTION & BATCH CSV
# ============================================================================

def test_transaction_ingestion_and_retrieval(client, merchant_headers, analyst_headers):
    """Verifies transaction creation via API key and retrieval via analyst JWT."""
    txn_id = f"TXN-BB-{uuid4().hex[:8]}"
    payload = {
        "customer_id": "CUST-BB-INGEST",
        "amount": 85.0,
        "currency": "USD",
        "payment_method": "card",
        "country": "US",
        "city": "Boston",
        "transaction_id": txn_id,
    }
    r = client.post("/api/transactions", json=payload, headers=merchant_headers)
    assert r.status_code == 201
    created = r.json()
    internal_id = created["id"]
    assert created["status"] in ("approved", "review", "blocked")

    # Fetch detail by internal ID
    r_get = client.get(f"/api/transactions/{internal_id}", headers=analyst_headers)
    assert r_get.status_code == 200
    detail = r_get.json()
    assert detail["id"] == internal_id
    assert detail["amount"] == 85.0

    # Retrieve associated risk assessment
    r_risk = client.get(f"/api/risk/{internal_id}", headers=analyst_headers)
    assert r_risk.status_code == 200
    assessment = r_risk.json()
    assert assessment["transaction_id"] == internal_id
    assert "risk_score" in assessment


def test_batch_csv_import_api(client, admin_headers):
    """Verifies batch CSV transaction import."""
    csv_content = (
        "transaction_id,customer_id,amount,currency,payment_method,country,city\n"
        f"CSV-001,CUST-CSV-A,50.0,USD,card,US,Seattle\n"
        f"CSV-002,CUST-CSV-B,75.0,USD,card,US,Portland\n"
    )
    files = {"file": ("transactions.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    r = client.post("/api/transactions/import/csv", files=files, headers=admin_headers)
    assert r.status_code == 200
    res = r.json()
    assert res["created"] == 2


# ============================================================================
# 4. ALERTS, INVESTIGATIONS & CUSTOMER RISK PROFILE
# ============================================================================

def test_alerts_and_investigation_lifecycle(client, admin_headers, analyst_headers):
    """Verifies alert review, case investigation creation, and unified detail view."""
    # 1. Ingest a transaction directly (manual transaction requires admin/business_manager)
    txn_res = client.post("/api/transactions/manual", json={
        "customer_id": "CUST-CASE-01",
        "amount": 250.0,
        "currency": "USD",
        "payment_method": "card",
        "country": "US",
    }, headers=admin_headers)
    assert txn_res.status_code == 201
    txn_id = txn_res.json()["id"]

    # 2. Create an alert for this transaction
    alert_res = client.post("/api/alerts", json={
        "transaction_id": txn_id,
        "title": "Manual investigation needed",
        "severity": "medium",
        "reason": "Test analyst alert creation",
    }, headers=analyst_headers)
    assert alert_res.status_code == 201
    alert_id = alert_res.json()["id"]

    # 3. Review the alert
    review_res = client.post(f"/api/alerts/{alert_id}/review", json={
        "status": "confirmed_fraud",
        "note": "Analyst verified fraudulent card misuse",
    }, headers=analyst_headers)
    assert review_res.status_code == 200
    assert review_res.json()["status"] == "confirmed_fraud"

    # 4. Create an investigation
    inv_res = client.post("/api/investigations", json={
        "transaction_id": txn_id,
        "notes": "Formal fraud investigation case",
    }, headers=analyst_headers)
    assert inv_res.status_code == 201
    inv_id = inv_res.json()["id"]

    # 5. Fetch Unified Investigation Detail View: GET /api/investigations/{id}
    inv_detail_res = client.get(f"/api/investigations/{inv_id}", headers=analyst_headers)
    assert inv_detail_res.status_code == 200
    inv_detail = inv_detail_res.json()
    assert inv_detail["id"] == inv_id
    assert inv_detail["transaction_id"] == txn_id
    assert "risk_assessment" in inv_detail
    assert isinstance(inv_detail["customer_history"], list)
    assert isinstance(inv_detail["related_alerts"], list)

    # 6. Read Dedicated Customer Risk Profile: GET /api/customers/{id}/risk-profile
    cust_id = inv_detail["customer_id"]
    profile_res = client.get(f"/api/customers/{cust_id}/risk-profile", headers=analyst_headers)
    assert profile_res.status_code == 200
    prof = profile_res.json()
    assert prof["customer_id"] == cust_id
    assert "risk_score" in prof
    assert "risk_level" in prof


# ============================================================================
# 5. AI INVESTIGATION ASSISTANT & DASHBOARD
# ============================================================================

def test_ai_investigation_assistant_api(client, analyst_headers):
    """Verifies natural language assistant answers analyst queries grounded in DB records."""
    r = client.post("/api/assistant/query", json={
        "query": "What are the risk factors for our customers?",
    }, headers=analyst_headers)
    assert r.status_code == 200
    ans = r.json()
    assert "answer" in ans
    assert len(ans["answer"]) > 10


def test_dashboard_and_analytics_apis(client, analyst_headers):
    """Verifies aggregated metrics and network graph endpoints."""
    # Dashboard summary
    r_dash = client.get("/api/dashboard", headers=analyst_headers)
    assert r_dash.status_code == 200
    dash = r_dash.json()
    assert "transactions" in dash
    assert "total" in dash["transactions"]
    assert "risk_summary" in dash

    # Network graph
    r_net = client.get("/api/network", headers=analyst_headers)
    assert r_net.status_code == 200
    net = r_net.json()
    assert "nodes" in net
    assert "edges" in net
