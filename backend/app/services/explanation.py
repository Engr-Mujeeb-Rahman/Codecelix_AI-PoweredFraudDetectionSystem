"""AI Explanation Service.

Generates plain-language, business-user understandable explanations for why a transaction
received its risk score and decision.
Scoring is deterministic at response time, LLM enhancement applied asynchronously after:
1. High-speed, deterministic template engine that formats exact bullet points per the PDF spec (<5ms).
2. Asynchronous LLM enhancement via Gemini / OpenAI applied post-response to update stored assessment.
"""
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def generate_deterministic_explanation(
    risk_score: float,
    risk_level: str,
    patterns: list[dict[str, Any]],
    triggered_rules: list[dict[str, Any]],
    customer_avg: float,
    customer_max: float,
    amount: float,
    is_new_device: bool,
    is_new_ip: bool,
) -> str:
    """Generates human-readable bullet points matching the exact style of the PDF specification."""
    bullets = []

    # 1. Amount comparison
    if customer_avg > 0 and amount >= customer_avg * 2.0:
        bullets.append(f"Customer normally spends ${customer_avg:,.0f}–${max(customer_max, customer_avg):,.0f}.")
        bullets.append(f"Current transaction is ${amount:,.2f}.")
    elif amount > 5000.0:
        bullets.append(f"High-value transaction amount: ${amount:,.2f}.")

    # 2. Device
    if is_new_device:
        bullets.append("New device detected.")

    # 3. Patterns
    for p in patterns:
        if not p.get("detected"):
            continue
        pat_name = p.get("pattern")
        details = p.get("details", {})
        msg = details.get("message")

        if pat_name == "location_anomaly" and msg:
            bullets.append(msg)
        elif pat_name == "rapid_transactions":
            count = details.get("count", 3)
            window = details.get("window_minutes", 5)
            bullets.append(f"{count} transactions occurred within {window} minutes.")
        elif pat_name == "device_sharing":
            count = details.get("shared_account_count", 2)
            bullets.append(f"Device is shared across {count} different customer accounts.")
        elif pat_name == "ip_sharing":
            count = details.get("shared_account_count", 3)
            bullets.append(f"Multiple customer accounts ({count}) using the same IP address.")
        elif pat_name == "behavior_change" and msg:
            bullets.append(msg)

    # 4. Triggered rules if not already covered
    for r in triggered_rules:
        r_name = r.get("name")
        if r_name and not any(r_name.lower() in b.lower() for b in bullets):
            bullets.append(f"Rule triggered: {r_name} (+{r.get('score_impact', 0):.0f} risk).")

    if not bullets:
        if risk_score <= settings.RISK_THRESHOLD_LOW:
            return f"Low Risk ({risk_score:.0f}/100): Transaction attributes align with established normal customer behavior."
        else:
            return f"{risk_level.title()} Risk ({risk_score:.0f}/100): Minor deviations from baseline activity detected."

    header = f"{risk_level.title()} Risk because:"
    bullet_text = "\n".join(f"• {b}" for b in bullets)
    return f"{header}\n{bullet_text}"


async def generate_llm_explanation(
    risk_score: float,
    risk_level: str,
    deterministic_text: str,
    transaction_summary: dict[str, Any],
) -> str:
    """Optionally enriches the explanation with an LLM summary if API keys are available."""
    api_key = settings.GEMINI_API_KEY or settings.OPENAI_API_KEY
    if not api_key:
        return deterministic_text

    try:
        prompt = (
            f"You are a fraud detection analyst. Explain in 2 concise sentences why this transaction was scored as {risk_level} Risk ({risk_score}/100).\n"
            f"Key facts:\n{deterministic_text}\n"
            f"Transaction data: {transaction_summary}\n"
            f"Keep it professional, direct, and understandable to a business manager."
        )

        async with httpx.AsyncClient(timeout=12.0) as client:
            if settings.GEMINI_API_KEY:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={settings.GEMINI_API_KEY}"
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    summary = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    return f"{summary}\n\n{deterministic_text}"

            elif settings.OPENAI_API_KEY:
                url = "https://api.openai.com/v1/chat/completions"
                headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 120,
                }
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    summary = data["choices"][0]["message"]["content"].strip()
                    return f"{summary}\n\n{deterministic_text}"

    except Exception as e:
        logger.warning("LLM explanation call failed, falling back to deterministic explanation: %s", e)

    return deterministic_text
