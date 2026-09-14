from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.device_usage import DeviceUsage
from app.models.transaction import Transaction

router = APIRouter()


@router.get("")
def fraud_network(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Customer -> Device -> IP relationship graph for visualization."""
    du_rows = (
        db.query(DeviceUsage, func.count(Transaction.id))
        .outerjoin(Transaction, Transaction.device_id == DeviceUsage.device_id)
        .group_by(DeviceUsage.id)
        .limit(500)
        .all()
    )
    customer_ids = {du.customer_id for du, _ in du_rows}
    device_ids = {du.device_id for du, _ in du_rows}

    txn_rows = (
        db.query(Transaction)
        .filter(Transaction.customer_id.in_(customer_ids) | Transaction.device_id.in_(device_ids))
        .limit(1000)
        .all()
    )

    nodes, edges = [], []
    seen_customers, seen_devices = set(), set()

    for du, txn_count in du_rows:
        if du.customer_id not in seen_customers:
            seen_customers.add(du.customer_id)
            nodes.append({"id": f"cust:{du.customer_id}", "type": "customer"})
        if du.device_id not in seen_devices:
            seen_devices.add(du.device_id)
            nodes.append({"id": f"dev:{du.device_id}", "type": "device"})
        edges.append({"source": f"cust:{du.customer_id}", "target": f"dev:{du.device_id}",
                      "relation": "used_device"})

    for t in txn_rows:
        if t.ip_address_str:
            ip_node = f"ip:{t.ip_address_str}"
            if ip_node not in [n["id"] for n in nodes]:
                nodes.append({"id": ip_node, "type": "ip", "label": t.ip_address_str})
            edges.append({"source": f"cust:{t.customer_id}", "target": ip_node,
                          "relation": "used_ip"})

    return {"nodes": nodes, "edges": edges}
