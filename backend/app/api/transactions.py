from datetime import datetime
from io import StringIO
import csv as csv_module

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session

from app.core.deps import get_api_client, get_current_user, require_roles
from app.crud.fraud import update_customer_profile
from app.crud.base import get_list, get_object
from app.db.session import get_db
from app.models.api_client import ApiClient
from app.models.customer import Customer
from app.models.transaction import Transaction, create_transaction_from_payload
from app.schemas.transaction import TransactionCreate, TransactionOut

router = APIRouter()


@router.post("", response_model=TransactionOut, status_code=201)
def create_transaction(
    data: TransactionCreate,
    db: Session = Depends(get_db),
    client: ApiClient = Depends(get_api_client),
):
    """External API: submit a transaction (creates customer/device/IP rows as needed)."""
    txn = create_transaction_from_payload(db, data.model_dump())
    update_customer_profile(db, txn.customer_id)
    client.requests_count += 1
    db.commit()
    db.refresh(txn)
    return txn


@router.get("", response_model=dict)
def list_transactions(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: str | None = None,
    status: str | None = None,
    payment_method: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    order_by: str = "created_at",
    order_dir: str = "desc",
):
    filters = {}
    if customer_id:
        c = (
            db.query(Customer)
            .filter((Customer.external_id == customer_id) | (Customer.id == customer_id))
            .first()
        )
        if not c:
            raise HTTPException(404, "Customer not found")
        filters["customer_id"] = c.id
    if status:
        filters["status"] = status
    if payment_method:
        filters["payment_method"] = payment_method

    result = get_list(
        db, Transaction, page=page, page_size=page_size, search=search,
        search_fields=("ip_address_str", "device_info", "id", "txn_external_id"),
        filters=filters, date_from=date_from, date_to=date_to,
        order_by=order_by, order_dir=order_dir,
    )
    if min_amount is not None:
        result["items"] = [t for t in result["items"] if t.amount >= min_amount]
    if max_amount is not None:
        result["items"] = [t for t in result["items"] if t.amount <= max_amount]
    result["items"] = [TransactionOut.model_validate(t).model_dump() for t in result["items"]]
    return result


@router.get("/{txn_id}", response_model=TransactionOut)
def get_transaction(txn_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return get_object(db, Transaction, txn_id)


@router.get("/{txn_id}/details")
def transaction_details(txn_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Complete view: transaction + customer + history + devices + IPs + related."""
    txn = get_object(db, Transaction, txn_id)
    customer = txn.customer
    history = (
        db.query(Transaction)
        .filter(Transaction.customer_id == customer.id, Transaction.id != txn.id)
        .order_by(Transaction.created_at.desc())
        .limit(20)
        .all()
    )
    devices = list(
        {t.device_id for t in history if t.device_id} | ({txn.device_id} if txn.device_id else set())
    )
    ips = list(
        {t.ip_address_str for t in history if t.ip_address_str}
        | ({txn.ip_address_str} if txn.ip_address_str else set())
    )
    related = []
    if txn.device_id:
        related += db.query(Transaction).filter(
            Transaction.device_id == txn.device_id, Transaction.customer_id != customer.id
        ).limit(10).all()
    if txn.ip_id:
        related += db.query(Transaction).filter(
            Transaction.ip_id == txn.ip_id, Transaction.customer_id != customer.id
        ).limit(10).all()
    return {
        "transaction": TransactionOut.model_validate(txn).model_dump(),
        "customer": {
            "id": customer.id,
            "external_id": customer.external_id,
            "email": customer.email,
            "total_transactions": customer.total_transactions,
        },
        "customer_history": [TransactionOut.model_validate(t).model_dump() for t in history],
        "devices": devices,
        "ip_addresses": ips,
        "related_transactions": [TransactionOut.model_validate(t).model_dump() for t in related],
    }


@router.post("/import/csv", response_model=dict)
async def import_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_roles("admin", "business_manager")),
):
    """Import transactions from CSV. Required columns: customer_id, amount."""
    content = await file.read()
    reader = csv_module.DictReader(StringIO(content.decode("utf-8-sig")))
    created, errors = 0, []
    for i, row in enumerate(reader, start=2):
        try:
            payload = {
                "customer_id": row["customer_id"],
                "amount": float(row["amount"]),
                "payment_method": row.get("payment_method") or "card",
                "ip_address": row.get("ip_address") or None,
                "device_id": row.get("device_id") or None,
                "country": row.get("country") or None,
                "city": row.get("city") or None,
                "device_info": row.get("device_info") or None,
                "transaction_id": row.get("transaction_id") or None,
                "created_at": row.get("created_at") or None,
            }
            txn = create_transaction_from_payload(db, payload)
            update_customer_profile(db, txn.customer_id)
            created += 1
        except Exception as e:
            errors.append({"line": i, "error": str(e)})
    db.commit()
    return {"created": created, "errors": errors[:20]}
