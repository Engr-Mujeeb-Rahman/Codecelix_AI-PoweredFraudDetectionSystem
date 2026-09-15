"""AI Investigation Assistant Service (Requirement 14).

Answers analyst inquiries using real database records:
- "Why is this customer suspicious?"
- "Show me unusual activity from this customer."
- "What transactions are connected to this device?"
- "Summarize this investigation."
Grounded strictly in actual platform data (no hallucinations).
"""
import json
import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.alert import Alert
from app.models.customer import Customer
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.device_usage import DeviceUsage
from app.models.investigation import Investigation
from app.models.risk_assessment import RiskAssessment
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)


def _retrieve_context(
    db: Session,
    customer_id: str | None = None,
    transaction_id: str | None = None,
    device_id: str | None = None,
    investigation_id: str | None = None,
) -> dict[str, Any]:
    """Retrieves relevant ground truth data from the DB for assistant queries."""
    context = {}

    # 1. Investigation context
    if investigation_id:
        inv = db.query(Investigation).filter(Investigation.id == investigation_id).first()
        if inv:
            context["investigation"] = {
                "id": inv.id,
                "status": inv.status,
                "notes": inv.notes,
                "conclusion": inv.conclusion,
                "created_at": str(inv.created_at),
                "closed_at": str(inv.closed_at),
                "analyst_id": inv.analyst_id,
            }
            if not customer_id:
                customer_id = inv.customer_id
            if not transaction_id:
                transaction_id = inv.transaction_id

    # 2. Transaction context
    if transaction_id:
        txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if txn:
            context["transaction"] = {
                "id": txn.id,
                "amount": txn.amount,
                "status": txn.status,
                "payment_method": txn.payment_method,
                "country": txn.country,
                "created_at": str(txn.created_at),
                "device_id": txn.device_id,
                "ip": txn.ip_address_str,
            }
            if not customer_id:
                customer_id = txn.customer_id
            assessment = db.query(RiskAssessment).filter(RiskAssessment.transaction_id == txn.id).first()
            if assessment:
                context["risk_assessment"] = {
                    "risk_score": assessment.risk_score,
                    "risk_level": assessment.risk_level,
                    "decision": assessment.decision,
                    "explanation": assessment.ai_explanation,
                }

    # 3. Customer context
    if customer_id:
        cust = (
            db.query(Customer)
            .filter((Customer.id == customer_id) | (Customer.external_id == customer_id))
            .first()
        )
        if cust:
            profile = db.query(CustomerRiskProfile).filter(CustomerRiskProfile.customer_id == cust.id).first()
            alerts = db.query(Alert).filter(Alert.customer_id == cust.id).limit(5).all()
            recent_txns = (
                db.query(Transaction)
                .filter(Transaction.customer_id == cust.id)
                .order_by(Transaction.created_at.desc())
                .limit(5)
                .all()
            )
            context["customer"] = {
                "id": cust.id,
                "external_id": cust.external_id,
                "total_transactions": cust.total_transactions,
                "suspicious_transactions": cust.suspicious_transactions,
                "previous_fraud_reports": cust.previous_fraud_reports,
                "avg_amount": cust.avg_amount,
                "max_amount": cust.max_amount,
                "risk_score": profile.risk_score if profile else None,
                "risk_level": profile.risk_level if profile else "LOW",
                "alerts_count": len(alerts),
                "recent_transactions": [
                    {"id": t.id, "amount": t.amount, "status": t.status, "country": t.country, "date": str(t.created_at)}
                    for t in recent_txns
                ],
            }

    # 4. Device context
    if device_id:
        usages = db.query(DeviceUsage).filter(DeviceUsage.device_id == device_id).all()
        dev_txns = db.query(Transaction).filter(Transaction.device_id == device_id).limit(10).all()
        context["device"] = {
            "device_id": device_id,
            "connected_accounts_count": len(usages),
            "connected_customer_ids": [u.customer_id for u in usages],
            "transaction_count": len(dev_txns),
            "transactions": [
                {"id": t.id, "customer_id": t.customer_id, "amount": t.amount, "status": t.status, "date": str(t.created_at)}
                for t in dev_txns
            ],
        }

    return context


def _deterministic_assistant_answer(query: str, context: dict[str, Any]) -> str:
    """Synthesizes structured, data-grounded answers to standard investigation queries."""
    q = query.lower()

    # Query: Connected to device
    if "device" in q and "device" in context:
        dev = context["device"]
        txns = dev.get("transactions", [])
        accts = dev.get("connected_customer_ids", [])
        txn_list = "\n".join(
            f"• Txn ID {t['id'][:8]}... | Amount: ${t['amount']:,.2f} | Status: {t['status']} | Customer: {t['customer_id'][:8]}..."
            for t in txns
        ) if txns else "• No transactions recorded on this device."
        return (
            f"Device '{dev['device_id']}' is linked to {dev['connected_accounts_count']} account(s) "
            f"and has processed {len(txns)} recorded transactions:\n\n{txn_list}"
        )

    # Query: Summarize investigation
    if ("investigation" in q or "summarize" in q) and "investigation" in context:
        inv = context["investigation"]
        cust = context.get("customer", {})
        txn = context.get("transaction", {})
        assessment = context.get("risk_assessment", {})
        return (
            f"Investigation Summary (ID: {inv['id']}):\n"
            f"• Status: {inv['status'].upper()}\n"
            f"• Customer: {cust.get('external_id', 'Unknown')} (Risk Level: {cust.get('risk_level', 'Unknown')})\n"
            f"• Flagged Transaction: ${txn.get('amount', 0):,.2f} ({txn.get('status', 'Unknown')})\n"
            f"• Risk Score: {assessment.get('risk_score', 'N/A')} ({assessment.get('risk_level', 'N/A')})\n"
            f"• Analyst Notes: {inv.get('notes') or 'No notes recorded.'}\n"
            f"• Conclusion: {inv.get('conclusion') or 'Under active review.'}"
        )

    # Query: Why is this customer suspicious?
    if "suspicious" in q and "customer" in context:
        cust = context["customer"]
        reasons = []
        if cust.get("suspicious_transactions", 0) > 0:
            reasons.append(f"{cust['suspicious_transactions']} transaction(s) marked suspicious/blocked.")
        if cust.get("previous_fraud_reports", 0) > 0:
            reasons.append(f"{cust['previous_fraud_reports']} confirmed fraud incident(s) reported.")
        if cust.get("risk_score", 0) and cust.get("risk_score") >= 70:
            reasons.append(f"High customer risk score: {cust['risk_score']}/100.")
        if cust.get("alerts_count", 0) > 0:
            reasons.append(f"{cust['alerts_count']} fraud alert(s) triggered.")

        recent = cust.get("recent_transactions", [])
        blocked = [t for t in recent if t["status"] in ("blocked", "review")]
        if blocked:
            reasons.append(f"Recent irregular transactions: {len(blocked)} under review/blocked.")

        if not reasons:
            return f"Customer {cust['external_id']} has a {cust['risk_level']} risk level with no severe fraud markers currently active."

        reason_text = "\n".join(f"• {r}" for r in reasons)
        return f"Customer {cust['external_id']} is flagged as suspicious due to:\n{reason_text}"

    # Query: Unusual activity
    if ("unusual" in q or "activity" in q) and "customer" in context:
        cust = context["customer"]
        recent = cust.get("recent_transactions", [])
        abnormal = [t for t in recent if t["status"] in ("blocked", "review") or t["amount"] > (cust.get("avg_amount", 0) * 2.5)]
        if abnormal:
            items = "\n".join(f"• ${t['amount']:,.2f} on {t['date'][:10]} ({t['status']})" for t in abnormal)
            return f"Unusual activity detected for {cust['external_id']}:\n{items}"
        return f"No unusual activity found for customer {cust['external_id']} in recent transactions."

    # General fallback based on retrieved context
    if "customer" in context:
        c = context["customer"]
        return f"Customer Profile: {c['external_id']} | Risk Level: {c['risk_level']} | Total Txns: {c['total_transactions']} | Avg Spend: ${c.get('avg_amount', 0):,.2f}."

    return "No specific records matched the query. Please provide a valid customer ID, transaction ID, or device ID."


async def ask_investigation_assistant(
    db: Session,
    query: str,
    customer_id: str | None = None,
    transaction_id: str | None = None,
    device_id: str | None = None,
    investigation_id: str | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """Grounded QA assistant. Returns (answer, mode, referenced_data)."""
    context = _retrieve_context(db, customer_id, transaction_id, device_id, investigation_id)
    deterministic_answer = _deterministic_assistant_answer(query, context)

    api_key = settings.GEMINI_API_KEY or settings.OPENAI_API_KEY
    if not api_key:
        return deterministic_answer, "deterministic_engine", context

    # Call LLM for enriched phrasing
    prompt = (
        "You are an AI Fraud Investigation Assistant. Answer the analyst's question strictly and accurately "
        "using ONLY the following database records. If the answer cannot be determined from the records, state so clearly.\n\n"
        f"Database Context:\n{json.dumps(context, indent=2)}\n\n"
        f"Analyst Question: {query}\n"
        "Provide a concise, direct, professional response citing exact IDs, amounts, and dates."
    )

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            if settings.GEMINI_API_KEY:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={settings.GEMINI_API_KEY}"
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    ans = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    return ans, "llm", context

            elif settings.OPENAI_API_KEY:
                url = "https://api.openai.com/v1/chat/completions"
                headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                }
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    ans = res.json()["choices"][0]["message"]["content"].strip()
                    return ans, "llm", context
    except Exception as e:
        logger.warning("LLM Assistant call failed, using deterministic engine: %s", e)

    return deterministic_answer, "deterministic_engine", context
