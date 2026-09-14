"""Generic CRUD helpers for FastAPI + SQLAlchemy."""
from typing import Any, Sequence

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

Model = Any


def _model_columns(model: Model) -> set[str]:
    return {c.key for c in inspect(model).mapper.column_attrs}


def get_list(
    db: Session,
    model: Model,
    *,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    search_fields: Sequence[str] = (),
    filters: dict[str, Any] | None = None,
    date_field: str = "created_at",
    date_from: Any = None,
    date_to: Any = None,
    order_by: str | None = None,
    order_dir: str = "desc",
):
    query = db.query(model)

    if filters:
        cols = _model_columns(model)
        for key, val in filters.items():
            if val is None or key not in cols:
                continue
            query = query.filter(getattr(model, key) == val)

    if search and search_fields:
        conds = [getattr(model, f).ilike(f"%{search}%") for f in search_fields]
        query = query.filter(or_(*conds))

    if date_from is not None:
        col = getattr(model, date_field, None)
        if col is not None:
            query = query.filter(col >= date_from)

    if date_to is not None:
        col = getattr(model, date_field, None)
        if col is not None:
            query = query.filter(col <= date_to)

    total = query.count()

    order_col = getattr(model, order_by or date_field, None) or getattr(model, date_field)
    query = query.order_by(order_col.desc() if order_dir == "desc" else order_col.asc())

    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def get_object(db: Session, model: Model, obj_id: str):
    obj = db.query(model).filter(model.id == obj_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return obj


def create_object(db: Session, model: Model, data: dict):
    obj = model(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_object(db: Session, obj, data: dict):
    for key, val in data.items():
        if val is not None and hasattr(obj, key):
            setattr(obj, key, val)
    db.commit()
    db.refresh(obj)
    return obj


def delete_object(db: Session, model: Model, obj_id: str):
    obj = get_object(db, model, obj_id)
    db.delete(obj)
    db.commit()
    return {"deleted": True, "id": obj_id}


def count_by(db: Session, model: Model, **filters) -> int:
    q = db.query(func.count(model.id))
    for k, v in filters.items():
        q = q.filter(getattr(model, k) == v)
    return q.scalar() or 0
