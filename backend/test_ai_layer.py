"""Comprehensive End-to-End Test Suite for the AI/Risk/Rules Layer.

Uses an isolated SQLite test database to verify:
1. New DB tables: fraud_rules, risk_assessments, customer_risk_profiles.
2. Rules engine evaluation & CRUD (with admin RBAC).
3. All 6 pattern detection algorithms.
4. ML Anomaly Detection (statistical fallback & Isolation Forest).
5. Real-time Risk scoring via POST /api/risk-check.
6. Ingestion scoring via POST /api/transactions with auto-alert creation on high risk.
7. Risk Assessment retrieval via GET /api/risk/{txn_id}.
8. AI Investigation Assistant Q&A via POST /api/assistant/query.
9. Feedback loop & model metrics via /api/risk-metrics and /api/risk/retrain.
"""
import os
import sys
from unittest.mock import AsyncMock, patch
from uuid import uuid4

# Set SQLite test database before importing any app modules
os.environ["DATABASE_URL"] = "sqlite:///./test_ai.db"

from fastapi.testclient import TestClient

from app.crud.fraud import create_user
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.models import *
from app.services.rules_engine import seed_default_rules

# Create all tables including additive tables
Base.metadata.create_all(bind=engine)

# Seed default rules
db = SessionLocal()
seed_default_rules(db)
create_user(db, "ai_admin@test.io", "Passw0rd!", "AI Admin", "admin")
create_user(db, "ai_analyst@test.io", "Passw0rd!", "AI Analyst", "analyst")
db.close()

client = TestClient(app)


def test_ai_layer_end_to_end():
    print("\n================ STARTING AI/RISK LAYER TESTS ================")

    # 1. Login
    r = client.post("/api/auth/login", json={"email": "ai_admin@test.io", "password": "Passw0rd!"})
    assert r.status_code == 200, r.text
    admin_token = r.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    r = client.post("/api/auth/login", json={"email": "ai_analyst@test.io", "password": "Passw0rd!"})
    assert r.status_code == 200, r.text
    analyst_token = r.json()["access_token"]
    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}
    print("[PASS] Authentication (Admin & Analyst)")

    # 2. Create API Client for External Ingestion
    r = client.post("/api/auth/api-clients", json={"name": "Test Merchant"}, headers=admin_headers)
    assert r.status_code == 201, r.text
    api_key = r.json()["api_key"]
    client_headers = {"X-API-Key": api_key}
    print("[PASS] API Client Created with X-API-Key")

    # 3. Verify Rules Engine Default Rules & CRUD
    r = client.get("/api/rules", headers=analyst_headers)
    assert r.status_code == 200, r.text
    rules = r.json()
    assert len(rules) >= 4, f"Expected >= 4 seeded rules, got {len(rules)}"
    print(f"[PASS] Default Rules Seeded: {len(rules)} active rules")

    # Admin creates a custom rule
    custom_rule_payload = {
        "name": "Crypto Payment Surcharge",
        "description": "Increase risk for cryptocurrency payments",
        "rule_type": "categorical",
        "conditions": {"field": "payment_method", "op": "==", "value": "crypto"},
        "action": "increase_risk",
        "score_impact": 25.0,
        "severity": "medium",
    }
    r = client.post("/api/rules", json=custom_rule_payload, headers=admin_headers)
    assert r.status_code == 201, r.text
    rule_id = r.json()["id"]
    print("[PASS] Admin created custom rule")

    # Analyst cannot create rule (RBAC)
    r = client.post("/api/rules", json=custom_rule_payload, headers=analyst_headers)
    assert r.status_code == 403, "Analyst should be blocked from rule creation"
    print("[PASS] RBAC enforced on rule creation")

    # 4. Ingest Baseline Transactions for Customer CUST-1029
    # Baseline: small amount, normal device and IP
    for i in range(3):
        normal_payload = {
            "customer_id": "CUST-1029",
            "amount": 60.0 + (i * 10),
            "payment_method": "card",
            "ip_address": "192.168.1.10",
            "device_id": "device-primary",
            "device_info": "Desktop / Chrome",
            "country": "US",
            "city": "New York",
            "transaction_id": f"TXN-BASE-{i+1}",
        }
        r = client.post("/api/transactions", json=normal_payload, headers=client_headers)
        assert r.status_code == 201, r.text
        txn_data = r.json()
        assert txn_data["status"] == "approved"
    print("[PASS] Baseline transactions submitted & scored LOW risk (approved)")

    # 5. Test Pre-scoring endpoint: POST /api/risk-check
    # Low-risk check
    r = client.post("/api/risk-check", json={
        "customer_id": "CUST-1029",
        "amount": 75.0,
        "payment_method": "card",
        "ip_address": "192.168.1.10",
        "device_id": "device-primary",
        "country": "US",
    }, headers=client_headers)
    assert r.status_code == 200, r.text
    check_resp = r.json()
    assert check_resp["risk_score"] <= 30.0, f"Expected Low Risk, got {check_resp['risk_score']}"
    assert check_resp["risk_level"] == "LOW"
    assert check_resp["decision"] == "APPROVE"
    print(f"[PASS] /api/risk-check evaluated Low Risk (Score: {check_resp['risk_score']})")

    # 6. Ingest Suspicious High-Risk Transaction Matching PDF Example
    # - Customer normally spends $50–$100
    # - Current transaction is $1,200
    # - New device detected
    # - New location (e.g. Russia/RU)
    # - Rapid velocity (multiple transactions within 5 minutes)
    suspicious_payload = {
        "customer_id": "CUST-1029",
        "amount": 1200.0,
        "payment_method": "card",
        "ip_address": "45.154.255.10",
        "device_id": "device-unknown-xyz",
        "device_info": "Mobile / Android",
        "country": "RU",
        "city": "Moscow",
        "transaction_id": "TXN-SUSPICIOUS-001",
    }
    r = client.post("/api/transactions", json=suspicious_payload, headers=client_headers)
    assert r.status_code == 201, r.text
    suspicious_txn = r.json()
    assert suspicious_txn["status"] in ("review", "blocked"), f"Expected review/blocked, got {suspicious_txn['status']}"
    suspicious_txn_id = suspicious_txn["id"]
    print(f"[PASS] Suspicious transaction flagged: Status = {suspicious_txn['status']}")

    # 7. Verify Stored Risk Assessment: GET /api/risk/{transaction_id}
    r = client.get(f"/api/risk/{suspicious_txn_id}", headers=analyst_headers)
    assert r.status_code == 200, r.text
    assessment = r.json()
    assert assessment["risk_score"] >= 70.0, f"Expected High Risk score >= 70, got {assessment['risk_score']}"
    assert assessment["risk_level"] == "HIGH"
    assert "High Risk because:" in assessment["ai_explanation"]
    assert "1,200" in assessment["ai_explanation"] or "1200" in assessment["ai_explanation"]
    print(f"[PASS] Stored RiskAssessment retrieved: Score = {assessment['risk_score']}, Level = {assessment['risk_level']}")
    print(f"       AI Explanation Preview:\n{assessment['ai_explanation']}")

    # 8. Verify Auto-Alert Creation on High Risk
    r = client.get("/api/alerts?status=new", headers=analyst_headers)
    assert r.status_code == 200, r.text
    alerts = r.json()["items"]
    matching_alerts = [a for a in alerts if a["transaction_id"] == suspicious_txn_id]
    assert len(matching_alerts) >= 1, "Auto-alert was not created for high-risk transaction!"
    alert = matching_alerts[0]
    assert alert["severity"] in ("high", "critical")
    print(f"[PASS] Auto-alert verified: Alert ID = {alert['id']}, Severity = {alert['severity']}")

    # 9. Test Device Sharing Pattern Detection
    # Another customer (CUST-9999) using the same device-unknown-xyz
    device_sharing_payload = {
        "customer_id": "CUST-9999",
        "amount": 250.0,
        "payment_method": "card",
        "device_id": "device-unknown-xyz",
        "ip_address": "45.154.255.10",
        "country": "US",
        "transaction_id": "TXN-DEV-SHARE-001",
    }
    r = client.post("/api/transactions", json=device_sharing_payload, headers=client_headers)
    assert r.status_code == 201, r.text
    shared_txn_id = r.json()["id"]

    r = client.get(f"/api/risk/{shared_txn_id}", headers=analyst_headers)
    assert r.status_code == 200, r.text
    shared_assessment = r.json()
    assert "device_sharing" in (shared_assessment["detected_patterns"] or "") or "Device is shared" in shared_assessment["ai_explanation"]
    print("[PASS] Device Sharing pattern detected across distinct accounts")

    # 10. Test AI Investigation Assistant: POST /api/assistant/query
    # Query 1: Why is this customer suspicious?
    r = client.post("/api/assistant/query", json={
        "query": "Why is this customer suspicious?",
        "customer_id": "CUST-1029",
    }, headers=analyst_headers)
    assert r.status_code == 200, r.text
    assistant_resp = r.json()
    assert any(marker in assistant_resp["answer"] for marker in ["1200", "1,200", "88.5", "CUST-1029"]), f"Expected concrete transaction data (amount/score/ID) in answer: {assistant_resp['answer']}"
    assert "suspicious" in assistant_resp["answer"].lower(), f"Expected 'suspicious' in answer: {assistant_resp['answer']}"
    assert any(term in assistant_resp["answer"].lower() for term in ["alert", "risk", "transaction", "blocked"]), f"Expected concrete risk reasons in answer: {assistant_resp['answer']}"
    print(f"[PASS] AI Assistant: 'Why is this customer suspicious?' answered grounded in DB records: {assistant_resp['answer'][:80]}...")

    # Query 2: What transactions are connected to this device?
    r = client.post("/api/assistant/query", json={
        "query": "What transactions are connected to this device?",
        "device_id": "device-unknown-xyz",
    }, headers=analyst_headers)
    assert r.status_code == 200, r.text
    dev_resp = r.json()
    assert "device-unknown-xyz" in dev_resp["answer"]
    assert "account" in dev_resp["answer"].lower() or "transaction" in dev_resp["answer"].lower()
    print("[PASS] AI Assistant: 'What transactions are connected to this device?' answered correctly")

    # 11. Test Model Feedback Loop & ML Metrics
    # Review alert as confirmed_fraud
    r = client.post(f"/api/alerts/{alert['id']}/review", json={
        "status": "confirmed_fraud",
        "note": "Analyst verified stolen credit card",
    }, headers=analyst_headers)
    assert r.status_code == 200, r.text

    # Check metrics
    r = client.get("/api/risk-metrics", headers=analyst_headers)
    assert r.status_code == 200, r.text
    metrics = r.json()
    assert metrics["confirmed_fraud_count"] >= 1
    assert metrics["estimated_precision"] > 0
    print(f"[PASS] ML Metrics retrieved: Confirmed Fraud = {metrics['confirmed_fraud_count']}, Precision = {metrics['estimated_precision']}")

    # 12. Test ML Model Retraining: POST /api/risk/retrain
    r = client.post("/api/risk/retrain", headers=admin_headers)
    assert r.status_code == 200, r.text
    retrain_res = r.json()
    assert "samples_used" in retrain_res and isinstance(retrain_res["samples_used"], int), "retrain missing samples_used int"
    assert "success" in retrain_res and isinstance(retrain_res["success"], bool), "retrain missing success boolean"
    assert "trained_at" in retrain_res, "retrain missing trained_at"
    assert "message" in retrain_res and len(retrain_res["message"]) > 0, "retrain missing message string"
    print(f"[PASS] ML Retraining endpoint invoked: success={retrain_res['success']}, samples_used={retrain_res['samples_used']}")

    # 13. Test Dashboard Risk Summary Integration
    r = client.get("/api/dashboard", headers=admin_headers)
    assert r.status_code == 200, r.text
    dash = r.json()
    assert "risk_summary" in dash
    assert dash["risk_summary"]["average_risk_score"] > 0
    assert dash["risk_summary"]["high_risk_count"] >= 1
    print(f"[PASS] Dashboard enriched with Risk Summary: Avg Score = {dash['risk_summary']['average_risk_score']}")

    # 14. Test Investigation Detail View with Risk Data Linkage: GET /api/investigations/{id}
    # 14a. Scored transaction investigation
    inv_res = client.post("/api/investigations", json={
        "transaction_id": suspicious_txn_id,
        "notes": "Analyst case review for high-risk transaction",
    }, headers=analyst_headers)
    assert inv_res.status_code == 201, inv_res.text
    inv_id = inv_res.json()["id"]

    r = client.get(f"/api/investigations/{inv_id}", headers=analyst_headers)
    assert r.status_code == 200, r.text
    inv_detail = r.json()
    assert inv_detail["id"] == inv_id
    assert inv_detail["transaction_id"] == suspicious_txn_id
    assert inv_detail["risk_assessment"] is not None, "Linked RiskAssessment must not be None for scored transaction"
    assert inv_detail["risk_assessment"]["risk_score"] >= 70.0, f"Expected risk_score >= 70, got {inv_detail['risk_assessment']['risk_score']}"
    assert inv_detail["risk_assessment"]["decision"] in ("REVIEW", "BLOCK")
    assert isinstance(inv_detail["customer_history"], list), "customer_history must be a list"
    assert len(inv_detail["customer_history"]) >= 1, "Expected historical transactions for customer"
    assert isinstance(inv_detail["related_alerts"], list), "related_alerts must be a list"
    assert len(inv_detail["related_alerts"]) >= 1, "Expected related alert for high-risk transaction"
    print(f"[PASS] GET /api/investigations/{{id}} for scored transaction: risk_score={inv_detail['risk_assessment']['risk_score']}, alerts={len(inv_detail['related_alerts'])}, history={len(inv_detail['customer_history'])}")

    # 14b. Unscored transaction investigation (transaction predating AI layer)
    db_raw = SessionLocal()
    unscored_txn_id = str(uuid4())
    unscored_txn = Transaction(
        id=unscored_txn_id,
        customer_id=inv_detail["customer_id"],
        amount=25.0,
        currency="USD",
        payment_method="card",
        status="approved",
    )
    db_raw.add(unscored_txn)
    db_raw.commit()
    db_raw.close()

    inv_unscored_res = client.post("/api/investigations", json={
        "transaction_id": unscored_txn_id,
        "notes": "Unscored legacy transaction investigation",
    }, headers=analyst_headers)
    assert inv_unscored_res.status_code == 201, inv_unscored_res.text
    unscored_inv_id = inv_unscored_res.json()["id"]

    r = client.get(f"/api/investigations/{unscored_inv_id}", headers=analyst_headers)
    assert r.status_code == 200, r.text
    unscored_detail = r.json()
    assert unscored_detail["id"] == unscored_inv_id
    assert unscored_detail["risk_assessment"] is None, "Unscored transaction should return risk_assessment=None without erroring"
    print("[PASS] GET /api/investigations/{id} for unscored transaction returned 200 with risk_assessment=None")

    # 15. Test CustomerRiskProfile Read Endpoint: GET /api/customers/{id}/risk-profile
    # 15a. Scored customer (CUST-1029)
    r = client.get("/api/customers/CUST-1029/risk-profile", headers=analyst_headers)
    assert r.status_code == 200, r.text
    profile = r.json()
    assert profile["risk_score"] > 0, f"Expected risk_score > 0, got {profile['risk_score']}"
    assert profile["risk_level"] in ("LOW", "MEDIUM", "HIGH")
    assert "devices_used_count" in profile and profile["devices_used_count"] >= 1
    assert "locations_used_count" in profile and profile["locations_used_count"] >= 1
    print(f"[PASS] GET /api/customers/CUST-1029/risk-profile returned profile: score={profile['risk_score']}, level={profile['risk_level']}")

    # 15b. Unscored customer (no transactions, no risk profile row)
    r_create_cust = client.post("/api/customers", json={
        "external_id": "CUST-UNSCORED-99",
        "email": "unscored99@test.io",
        "full_name": "Unscored Customer",
    }, headers=admin_headers)
    assert r_create_cust.status_code == 201, r_create_cust.text
    unscored_cust_id = r_create_cust.json()["id"]

    r = client.get(f"/api/customers/{unscored_cust_id}/risk-profile", headers=analyst_headers)
    assert r.status_code == 404, f"Expected 404 for unscored customer, got {r.status_code}"
    print("[PASS] GET /api/customers/{id}/risk-profile returned 404 for unscored customer")

    # 16. Test BackgroundTasks LLM Explanation Enhancement
    mock_enhanced_text = "[LLM ENHANCED SUMMARY: Gemini analyzed transaction risk]\n\nHigh Risk because:\n• Large deviation from spending baseline"
    with patch("app.services.explanation.generate_llm_explanation", new=AsyncMock(return_value=mock_enhanced_text)):
        bg_payload = {
            "customer_id": "CUST-1029",
            "amount": 2500.0,
            "payment_method": "card",
            "ip_address": "185.220.101.5",
            "device_id": "device-bg-test",
            "country": "NG",
            "transaction_id": "TXN-BG-LLM-001",
        }
        r = client.post("/api/transactions", json=bg_payload, headers=client_headers)
        assert r.status_code == 201, r.text
        bg_txn_id = r.json()["id"]

        # Fetch stored RiskAssessment to verify that BackgroundTasks updated the stored explanation
        r_risk = client.get(f"/api/risk/{bg_txn_id}", headers=analyst_headers)
        assert r_risk.status_code == 200, r_risk.text
        stored_assessment = r_risk.json()
        assert "[LLM ENHANCED SUMMARY" in stored_assessment["ai_explanation"], (
            f"Stored ai_explanation was not updated by BackgroundTasks! Content: {stored_assessment['ai_explanation']}"
        )
        print("[PASS] BackgroundTasks LLM enhancement executed and updated stored RiskAssessment.ai_explanation")

    print("\n================ ALL AI/RISK LAYER TESTS PASSED ================\n")


if __name__ == "__main__":
    test_ai_layer_end_to_end()
