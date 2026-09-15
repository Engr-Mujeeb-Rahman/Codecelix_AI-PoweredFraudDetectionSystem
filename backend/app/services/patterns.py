"""Fraud Pattern Detection Service.

Detects the 6 fraud patterns specified in the assignment:
1. Rapid Transactions: multiple transactions within a short time window (e.g. 5 min).
2. Device Sharing: multiple customer accounts sharing the same device.
3. IP Sharing: multiple customer accounts sharing the same IP.
4. Location Anomaly: transactions from new/unusual or impossible locations.
5. Account Behavior Change: deviation from historical velocity or activity timing.
6. Transaction Amount Anomaly: transaction amount significantly deviating from normal spending.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.device import Device
from app.models.device_usage import DeviceUsage
from app.models.ip_address import IpAddress
from app.models.transaction import Transaction
from app.utils.datetime import utcnow


def _aware(dt: datetime | None) -> datetime:
    if dt is None:
        return utcnow()
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def detect_rapid_transactions(
    db: Session,
    customer_id: str,
    current_time: datetime,
    window_minutes: int = 5,
    threshold: int = 3,
    exclude_txn_id: str | None = None,
) -> dict[str, Any]:
    """Detects if customer performed >= threshold transactions within window_minutes."""
    time_window_start = _aware(current_time) - timedelta(minutes=window_minutes)

    q = (
        db.query(func.count(Transaction.id))
        .filter(
            Transaction.customer_id == customer_id,
            Transaction.created_at >= time_window_start,
        )
    )
    if exclude_txn_id:
        q = q.filter(Transaction.id != exclude_txn_id)

    count = (q.scalar() or 0) + 1  # include current transaction

    detected = count >= threshold
    return {
        "pattern": "rapid_transactions",
        "detected": detected,
        "score_contribution": 25.0 if detected else 0.0,
        "details": {
            "window_minutes": window_minutes,
            "count": count,
            "threshold": threshold,
            "message": f"{count} transactions occurred within {window_minutes} minutes"
            if detected
            else "Normal transaction frequency",
        },
    }


def detect_device_sharing(
    db: Session,
    device_id: str | None,
    customer_id: str,
) -> dict[str, Any]:
    """Detects if multiple customer accounts use the same device."""
    if not device_id:
        return {
            "pattern": "device_sharing",
            "detected": False,
            "score_contribution": 0.0,
            "details": {"message": "No device ID provided"},
        }

    # Resolve device if fingerprint or UUID passed
    dev = db.query(Device).filter((Device.id == device_id) | (Device.fingerprint == device_id)).first()
    target_id = dev.id if dev else device_id

    # Count distinct customers that have used this device
    shared_customers = (
        db.query(DeviceUsage.customer_id)
        .filter(DeviceUsage.device_id == target_id)
        .distinct()
        .all()
    )
    account_ids = {c[0] for c in shared_customers}
    account_ids.add(customer_id)
    count = len(account_ids)

    detected = count > 1
    return {
        "pattern": "device_sharing",
        "detected": detected,
        "score_contribution": 30.0 if detected else 0.0,
        "details": {
            "shared_account_count": count,
            "device_id": device_id,
            "message": f"Device is shared across {count} customer accounts"
            if detected
            else "Device is exclusive to this customer",
        },
    }


def detect_ip_sharing(
    db: Session,
    ip_str: str | None,
    customer_id: str,
    threshold: int = 3,
) -> dict[str, Any]:
    """Detects if a suspicious number of accounts use the same IP address."""
    if not ip_str:
        return {
            "pattern": "ip_sharing",
            "detected": False,
            "score_contribution": 0.0,
            "details": {"message": "No IP address provided"},
        }

    # Check distinct customers associated with this IP
    distinct_customers = (
        db.query(Transaction.customer_id)
        .filter(Transaction.ip_address_str == ip_str)
        .distinct()
        .all()
    )
    cust_set = {c[0] for c in distinct_customers}
    cust_set.add(customer_id)
    count = len(cust_set)

    detected = count >= threshold
    return {
        "pattern": "ip_sharing",
        "detected": detected,
        "score_contribution": 25.0 if detected else 0.0,
        "details": {
            "shared_account_count": count,
            "ip_address": ip_str,
            "threshold": threshold,
            "message": f"IP address is used by {count} distinct accounts"
            if detected
            else "Normal IP usage count",
        },
    }


def detect_location_anomaly(
    db: Session,
    customer: Customer,
    country: str | None,
    city: str | None,
    current_time: datetime,
    exclude_txn_id: str | None = None,
) -> dict[str, Any]:
    """Detects transactions from new, unusual, or impossible locations."""
    if not country:
        return {
            "pattern": "location_anomaly",
            "detected": False,
            "score_contribution": 0.0,
            "details": {"message": "No location provided"},
        }

    # Query customer's past transactions
    q = db.query(Transaction).filter(Transaction.customer_id == customer.id)
    if exclude_txn_id:
        q = q.filter(Transaction.id != exclude_txn_id)
    past_txns = q.order_by(Transaction.created_at.desc()).limit(20).all()

    if not past_txns:
        return {
            "pattern": "location_anomaly",
            "detected": False,
            "score_contribution": 0.0,
            "details": {"message": "First transaction for customer (no location history)"},
        }

    known_countries = {t.country for t in past_txns if t.country}
    last_txn = past_txns[0]
    is_new_country = country not in known_countries if known_countries else False

    # Check impossible travel (different country within 2 hours)
    impossible_travel = False
    if last_txn.country and last_txn.country != country and last_txn.created_at:
        time_diff = abs((_aware(current_time) - _aware(last_txn.created_at)).total_seconds())
        if time_diff < 7200:  # less than 2 hours
            impossible_travel = True

    detected = is_new_country or impossible_travel
    score = 35.0 if impossible_travel else (20.0 if is_new_country else 0.0)

    msg = (
        f"Impossible travel detected: {last_txn.country} to {country} in < 2 hours"
        if impossible_travel
        else (f"Login location ({country}) is different from previous activity" if is_new_country else "Consistent location")
    )

    return {
        "pattern": "location_anomaly",
        "detected": detected,
        "score_contribution": score,
        "details": {
            "country": country,
            "known_countries": list(known_countries),
            "impossible_travel": impossible_travel,
            "message": msg,
        },
    }


def detect_amount_anomaly(
    customer: Customer,
    amount: float,
) -> dict[str, Any]:
    """Detects if transaction amount significantly differs from customer spending habits."""
    avg = customer.avg_amount or 0.0
    max_amt = customer.max_amount or 0.0
    total_txns = customer.total_transactions or 0

    if total_txns < 2:
        # For new accounts, check if transaction is high-value
        is_high_new = amount >= 1000.0
        return {
            "pattern": "amount_anomaly",
            "detected": is_high_new,
            "score_contribution": 30.0 if is_high_new else 0.0,
            "details": {
                "amount": amount,
                "customer_avg": avg,
                "is_new_account": True,
                "message": f"High-value transaction (${amount:,.2f}) from a new account"
                if is_high_new
                else "Normal initial transaction amount",
            },
        }

    # Established customer: check deviation from normal spending
    is_anomaly = False
    ratio = amount / (avg + 0.01)

    if avg > 0 and (ratio >= 3.0 or (max_amt > 0 and amount >= max_amt * 2.0)):
        is_anomaly = True

    score = min(40.0, max(0.0, (ratio - 1.0) * 10.0)) if is_anomaly else 0.0

    return {
        "pattern": "amount_anomaly",
        "detected": is_anomaly,
        "score_contribution": score,
        "details": {
            "amount": amount,
            "customer_avg": round(avg, 2),
            "customer_max": round(max_amt, 2),
            "ratio_to_avg": round(ratio, 2),
            "message": f"Customer normally spends ${avg:,.0f}–${max_amt:,.0f}. Current transaction is ${amount:,.2f}"
            if is_anomaly
            else "Transaction amount matches normal spending habits",
        },
    }


def detect_behavior_change(
    customer: Customer,
    amount: float,
    current_time: datetime,
) -> dict[str, Any]:
    """Compares current transaction characteristics with customer's historical behavior."""
    velocity_spike = False
    now = _aware(current_time)

    if customer.txn_velocity_24h > 0:
        avg_hourly_in_24h = customer.txn_velocity_24h / 24.0
        if customer.txn_velocity_1h >= max(3, avg_hourly_in_24h * 4):
            velocity_spike = True

    # Check sudden activity after prolonged inactivity (> 30 days)
    dormant_reactivation = False
    if customer.last_txn_at:
        days_since_last = (now - _aware(customer.last_txn_at)).days
        if days_since_last > 30 and amount > 500.0:
            dormant_reactivation = True

    detected = velocity_spike or dormant_reactivation
    score = 25.0 if detected else 0.0

    msg = (
        "Sudden spike in transaction frequency"
        if velocity_spike
        else ("High-value activity on a previously dormant account" if dormant_reactivation else "Customer behavior aligns with historical patterns")
    )

    return {
        "pattern": "behavior_change",
        "detected": detected,
        "score_contribution": score,
        "details": {
            "velocity_1h": customer.txn_velocity_1h,
            "velocity_24h": customer.txn_velocity_24h,
            "velocity_spike": velocity_spike,
            "dormant_reactivation": dormant_reactivation,
            "message": msg,
        },
    }


def run_all_pattern_checks(
    db: Session,
    customer: Customer,
    amount: float,
    device_id: str | None,
    ip_str: str | None,
    country: str | None,
    city: str | None,
    current_time: datetime,
    exclude_txn_id: str | None = None,
) -> list[dict[str, Any]]:
    """Runs all 6 pattern detection algorithms and returns structured results."""
    return [
        detect_rapid_transactions(db, customer.id, current_time, exclude_txn_id=exclude_txn_id),
        detect_device_sharing(db, device_id, customer.id),
        detect_ip_sharing(db, ip_str, customer.id),
        detect_location_anomaly(db, customer, country, city, current_time, exclude_txn_id=exclude_txn_id),
        detect_amount_anomaly(customer, amount),
        detect_behavior_change(customer, amount, current_time),
    ]
