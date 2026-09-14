from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value
    s = str(value).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
