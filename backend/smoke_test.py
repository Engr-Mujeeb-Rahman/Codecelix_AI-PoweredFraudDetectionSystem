"""End-to-end smoke test using SQLite (no Postgres needed).

Run: python smoke_test.py
"""
import os

# Must be set BEFORE importing app modules
os.environ["DATABASE_URL"] = "sqlite:///./smoke_test.db"

from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import Base, engine, SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import *  # noqa: F401,F403
from app.crud.fraud import create_user  # noqa: E402

Base.metadata.create_all(bind=engine)

client = TestClient(app)
db = SessionLocal()
create_user(db, "admin@test.io", "Passw0rd!", "Admin", "admin")
create_user(db, "analyst@test.io", "Passw0rd!", "Analyst", "analyst")
db.close()

# --- 1. Login ---
r = client.post("/api/auth/login", json={"email": "admin@test.io", "password": "Passw0rd!"})
assert r.status_code == 200, r.text
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}
print("PASS login")

# --- 2. Create API client ---
r = client.post("/api/auth/api-clients", json={"name": "Shopify Store"}, headers=H)
assert r.status_code == 201, r.text
api_key = r.json()["api_key"]
print("PASS create api client")

# --- 3. Submit transactions via external API ---
normal_txn = {
    "customer_id": "CUST-1001",
    "amount": 55.00,
    "payment_method": "card",
    "ip_address": "10.0.1.5",
    "device_id": "dev-abc",
    "device_info": "desktop / Windows",
    "country": "US",
    "transaction_id": "TXN-EXT-001",
}
r = client.post("/api/transactions", json=normal_txn, headers={"X-API-Key": api_key})
assert r.status_code == 201, r.text
print("PASS create transaction:", r.json()["txn_external_id"])

r = client.post("/api/transactions", json={
    "customer_id": "CUST-1001", "amount": 120.00, "payment_method": "wallet",
    "ip_address": "10.0.1.5", "device_id": "dev-abc", "transaction_id": "TXN-EXT-002",
}, headers={"X-API-Key": api_key})
assert r.status_code == 201, r.text
print("PASS second transaction")

# --- 4. List + search + details ---
r = client.get("/api/transactions?page=1&page_size=10&search=TXN-EXT", headers=H)
assert r.status_code == 200 and r.json()["total"] == 2, r.text
print("PASS list+search transactions:", r.json()["total"])

txn_id = r.json()["items"][0]["id"]
r = client.get(f"/api/transactions/{txn_id}", headers=H)
assert r.status_code == 200
r = client.get(f"/api/transactions/{txn_id}/details", headers=H)
assert r.status_code == 200 and r.json()["customer"]["external_id"] == "CUST-1001"
print("PASS get + details")

# --- 5. Customer profile auto-updated ---
r = client.get("/api/customers", headers=H)
assert r.status_code == 200 and r.json()["total"] == 1, r.text
c = r.json()["items"][0]
assert c["total_transactions"] == 2 and c["avg_amount"] == 87.5, c
print("PASS customer profile aggregates:", c["total_transactions"], "txns, avg", c["avg_amount"])

# --- 6. CSV import ---
csv_content = (
    "customer_id,amount,payment_method,ip_address,country\n"
    "CUST-2002,75.50,card,10.0.2.8,US\n"
    "CUST-2002,30.00,wallet,10.0.2.8,US\n"
)
import io
r = client.post("/api/transactions/import/csv",
                files={"file": ("txns.csv", io.BytesIO(csv_content.encode()), "text/csv")},
                headers=H)
assert r.status_code == 200 and r.json()["created"] == 2, r.text
print("PASS CSV import:", r.json()["created"])

# --- 7. Alerts CRUD + review + feedback ---
r = client.get("/api/transactions?page_size=1", headers=H)
txn_id = r.json()["items"][0]["id"]
r = client.post("/api/alerts", json={"transaction_id": txn_id, "title": "Suspicious activity",
                                     "reason": "Manual review needed", "severity": "high"}, headers=H)
assert r.status_code == 201, r.text
alert_id = r.json()["id"]
print("PASS create alert")

r = client.post(f"/api/alerts/{alert_id}/review", json={"status": "confirmed_fraud", "note": "verified"},
                headers=H)
assert r.status_code == 200 and r.json()["status"] == "confirmed_fraud", r.text
print("PASS alert review")

r = client.get("/api/feedback", headers=H)
assert r.status_code == 200 and len(r.json()) >= 1, r.text
print("PASS feedback recorded")

r = client.post(f"/api/alerts/{alert_id}/review", json={"status": "bogus"}, headers=H)
assert r.status_code == 400
print("PASS invalid status rejected")

# --- 8. Investigations ---
r = client.post("/api/investigations", json={"transaction_id": txn_id, "notes": "checking device sharing"},
                headers=H)
assert r.status_code == 201, r.text
print("PASS create investigation")

# --- 9. Dashboard ---
r = client.get("/api/dashboard", headers=H)
assert r.status_code == 200, r.text
d = r.json()
assert d["transactions"]["total"] == 4, d
print("PASS dashboard:", d["transactions"])

# --- 10. Network graph ---
r = client.get("/api/network", headers=H)
assert r.status_code == 200, r.text
print("PASS network graph:", len(r.json()["nodes"]), "nodes")

# --- 11. Reports ---
r = client.post("/api/reports", json={"report_type": "daily_activity"}, headers=H)
assert r.status_code == 201, r.text
report_id = r.json()["id"]
r = client.get(f"/api/reports/{report_id}/export?format=csv", headers=H)
assert r.status_code == 200
print("PASS reports + export")

# --- 12. RBAC: analyst cannot create customers or review in admin-only areas ---
r = client.post("/api/auth/login", json={"email": "analyst@test.io", "password": "Passw0rd!"})
AH = {"Authorization": f"Bearer {r.json()['access_token']}"}
r = client.post("/api/customers", json={"external_id": "X-1"}, headers=AH)
assert r.status_code == 403, r.text
print("PASS RBAC: analyst blocked from customer creation")

r = client.get("/api/transactions")
assert r.status_code == 401
print("PASS auth required")

print("\nALL SMOKE TESTS PASSED OK")
