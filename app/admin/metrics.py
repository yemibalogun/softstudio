"""
Read side of the dashboard: every number on the page comes from here.

Kept out of the routes so the same figures can be rendered into the page on
first load and returned as JSON to the poller, with no duplicated SQL.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models import (
    DownloadRequest, ErrorEvent, PageView, Product, ProjectInquiry,
    ServiceSubscription, WaitlistSubscriber,
)
from app.models.subscription import upcoming

# Ranges the dashboard offers, and how their series are bucketed.
RANGES = {
    "24h": {"hours": 24, "bucket": "hour", "label": "Last 24 hours"},
    "7d": {"hours": 24 * 7, "bucket": "day", "label": "Last 7 days"},
    "30d": {"hours": 24 * 30, "bucket": "day", "label": "Last 30 days"},
}
DEFAULT_RANGE = "24h"


def _since(range_key: str) -> datetime:
    hours = RANGES.get(range_key, RANGES[DEFAULT_RANGE])["hours"]
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def _count_since(model, since: datetime, column=None) -> int:
    column = column if column is not None else model.created_at
    return db.session.query(func.count(model.id)).filter(column >= since).scalar() or 0


def traffic_series(range_key: str) -> list[dict]:
    """Views and unique visitors per bucket, zero-filled so charts never gap."""
    spec = RANGES.get(range_key, RANGES[DEFAULT_RANGE])
    since = _since(range_key)
    by_hour = spec["bucket"] == "hour"
    step = timedelta(hours=1) if by_hour else timedelta(days=1)

    rows = (
        db.session.query(
            func.date_trunc(spec["bucket"], PageView.created_at).label("bucket"),
            func.count(PageView.id),
            func.count(func.distinct(PageView.visitor_hash)),
        )
        .filter(PageView.created_at >= since)
        .group_by("bucket")
        .all()
    ) if db.engine.name == "postgresql" else _series_fallback(since, by_hour)

    found = {}
    for bucket, views, visitors in rows:
        if isinstance(bucket, str):  # SQLite returns text
            bucket = datetime.fromisoformat(bucket)
        if bucket.tzinfo is None:
            bucket = bucket.replace(tzinfo=timezone.utc)
        found[bucket.replace(minute=0, second=0, microsecond=0) if by_hour
              else bucket.replace(hour=0, minute=0, second=0, microsecond=0)] = (views, visitors)

    now = datetime.now(timezone.utc)
    start = (now.replace(minute=0, second=0, microsecond=0) if by_hour
             else now.replace(hour=0, minute=0, second=0, microsecond=0)) - step * (
        spec["hours"] - 1 if by_hour else spec["hours"] // 24 - 1)

    series = []
    cursor = start
    while cursor <= now:
        views, visitors = found.get(cursor, (0, 0))
        series.append({
            "at": cursor.isoformat(),
            "label": cursor.strftime("%H:%M" if by_hour else "%b %d"),
            "views": views,
            "visitors": visitors,
        })
        cursor += step
    return series


def _series_fallback(since: datetime, by_hour: bool):
    """SQLite has no date_trunc; bucket in Python instead (tests, local runs)."""
    fmt = "%Y-%m-%d %H:00:00" if by_hour else "%Y-%m-%d 00:00:00"
    rows = (
        db.session.query(PageView.created_at, PageView.visitor_hash)
        .filter(PageView.created_at >= since)
        .all()
    )
    buckets: dict[str, list] = {}
    for created_at, visitor in rows:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        key = created_at.strftime(fmt)
        entry = buckets.setdefault(key, [0, set()])
        entry[0] += 1
        entry[1].add(visitor)
    return [(datetime.strptime(k, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc), v[0], len(v[1]))
            for k, v in buckets.items()]


def top_pages(since: datetime, limit: int = 8) -> list[dict]:
    rows = (
        db.session.query(PageView.path, func.count(PageView.id).label("views"))
        .filter(PageView.created_at >= since)
        .group_by(PageView.path)
        .order_by(func.count(PageView.id).desc())
        .limit(limit)
        .all()
    )
    return [{"path": path, "views": views} for path, views in rows]


def top_sources(since: datetime, limit: int = 6) -> list[dict]:
    rows = (
        db.session.query(PageView.source, func.count(PageView.id).label("views"))
        .filter(PageView.created_at >= since)
        .group_by(PageView.source)
        .order_by(func.count(PageView.id).desc())
        .limit(limit)
        .all()
    )
    return [{"source": source or "direct", "views": views} for source, views in rows]


def device_split(since: datetime) -> list[dict]:
    rows = (
        db.session.query(PageView.device, func.count(PageView.id))
        .filter(PageView.created_at >= since)
        .group_by(PageView.device)
        .all()
    )
    total = sum(count for _, count in rows) or 1
    return [
        {"device": device or "desktop", "views": count, "percent": round(count * 100 / total)}
        for device, count in sorted(rows, key=lambda r: -r[1])
    ]


def product_performance(since: datetime, limit: int = 6) -> list[dict]:
    """Views and download requests per product, most viewed first."""
    views = dict(
        db.session.query(PageView.product_id, func.count(PageView.id))
        .filter(PageView.created_at >= since, PageView.product_id.isnot(None))
        .group_by(PageView.product_id)
        .all()
    )
    downloads = dict(
        db.session.query(DownloadRequest.product_id, func.count(DownloadRequest.id))
        .filter(DownloadRequest.created_at >= since)
        .group_by(DownloadRequest.product_id)
        .all()
    )
    signups = dict(
        db.session.query(WaitlistSubscriber.product_id, func.count(WaitlistSubscriber.id))
        .filter(WaitlistSubscriber.created_at >= since)
        .group_by(WaitlistSubscriber.product_id)
        .all()
    )

    product_ids = set(views) | set(downloads) | set(signups)
    if not product_ids:
        return []
    products = Product.query.filter(Product.id.in_(product_ids)).all()
    rows = [
        {
            "id": p.id,
            "title": p.title,
            "slug": p.slug,
            "views": views.get(p.id, 0),
            "downloads": downloads.get(p.id, 0),
            "signups": signups.get(p.id, 0),
        }
        for p in products
    ]
    rows.sort(key=lambda r: (-r["views"], -r["downloads"]))
    return rows[:limit]


def emails_collected(since: datetime) -> dict:
    """Every way an address reaches us, counted in one place."""
    waitlist = _count_since(WaitlistSubscriber, since)
    downloads = _count_since(DownloadRequest, since)
    inquiries = _count_since(ProjectInquiry, since)
    return {
        "waitlist": waitlist,
        "downloads": downloads,
        "inquiries": inquiries,
        "total": waitlist + downloads + inquiries,
        "all_time": (
            db.session.query(func.count(WaitlistSubscriber.id)).scalar() or 0
        ) + (
            db.session.query(func.count(DownloadRequest.id)).scalar() or 0
        ) + (
            db.session.query(func.count(ProjectInquiry.id)).scalar() or 0
        ),
    }


def recent_signups(limit: int = 8) -> list[dict]:
    """Latest addresses collected, newest first, across both funnels."""
    items: list[dict] = []
    for sub in (WaitlistSubscriber.query
                .order_by(WaitlistSubscriber.created_at.desc()).limit(limit).all()):
        items.append({
            "email": sub.email, "name": sub.name, "kind": "waitlist",
            "source": sub.source or "direct", "at": sub.created_at,
            "product": sub.product.title if sub.product else None,
        })
    for req in (DownloadRequest.query
                .order_by(DownloadRequest.created_at.desc()).limit(limit).all()):
        items.append({
            "email": req.email, "name": req.name, "kind": "download",
            "source": req.source or "direct", "at": req.created_at,
            "product": req.product.title if req.product else None,
        })
    items.sort(key=lambda i: i["at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return items[:limit]


def error_summary(since: datetime, limit: int = 8) -> dict:
    counts = dict(
        db.session.query(ErrorEvent.kind, func.coalesce(func.sum(ErrorEvent.occurrences), 0))
        .filter(ErrorEvent.last_seen >= since)
        .group_by(ErrorEvent.kind)
        .all()
    )
    recent = (
        ErrorEvent.query.filter(ErrorEvent.last_seen >= since)
        .order_by(ErrorEvent.last_seen.desc())
        .limit(limit)
        .all()
    )
    return {
        "counts": {kind: int(counts.get(kind, 0)) for kind in ErrorEvent.KINDS},
        "total": int(sum(counts.values())),
        "unresolved": ErrorEvent.query.filter_by(resolved=False).count(),
        "recent": [
            {
                "id": e.id, "kind": e.kind, "status_code": e.status_code,
                "message": e.message, "path": e.path, "occurrences": e.occurrences,
                "last_seen": e.last_seen, "resolved": e.resolved,
            }
            for e in recent
        ],
    }


def renewals(window_days: int = 60) -> dict:
    """What is due soon, and what the whole stack costs."""
    due = upcoming(window_days)
    active = ServiceSubscription.query.filter_by(is_active=True).all()

    monthly: dict[str, Decimal] = {}
    for sub in active:
        monthly[sub.currency] = monthly.get(sub.currency, Decimal("0")) + sub.monthly_cost

    return {
        "due": [
            {
                "id": s.id, "name": s.name, "vendor": s.vendor, "category": s.category,
                "amount": float(s.amount or 0), "currency": s.currency,
                "cycle": s.cycle, "due_on": s.next_due_on,
                "days_until_due": s.days_until_due, "is_overdue": s.is_overdue,
            }
            for s in due
        ],
        "overdue_count": sum(1 for s in due if s.is_overdue),
        "monthly_by_currency": {code: float(total) for code, total in sorted(monthly.items())},
        "yearly_by_currency": {code: float(total * 12) for code, total in sorted(monthly.items())},
        "active_count": len(active),
    }


def live_counters() -> dict:
    """The small 'right now' numbers at the top of the page."""
    now = datetime.now(timezone.utc)
    five_min = now - timedelta(minutes=5)
    today = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    return {
        "online_now": db.session.query(func.count(func.distinct(PageView.visitor_hash)))
        .filter(PageView.created_at >= five_min).scalar() or 0,
        "views_today": _count_since(PageView, today),
        "visitors_today": db.session.query(func.count(func.distinct(PageView.visitor_hash)))
        .filter(PageView.created_at >= today).scalar() or 0,
    }


def dashboard_data(range_key: str = DEFAULT_RANGE) -> dict:
    """Everything the dashboard shows, for both the page and the poller."""
    range_key = range_key if range_key in RANGES else DEFAULT_RANGE
    since = _since(range_key)
    spec = RANGES[range_key]

    views = _count_since(PageView, since)
    visitors = db.session.query(func.count(func.distinct(PageView.visitor_hash))).filter(
        PageView.created_at >= since).scalar() or 0

    return {
        "range": range_key,
        "range_label": spec["label"],
        "generated_at": datetime.now(timezone.utc),
        "live": live_counters(),
        "totals": {"views": views, "visitors": visitors},
        "series": traffic_series(range_key),
        "top_pages": top_pages(since),
        "top_sources": top_sources(since),
        "devices": device_split(since),
        "products": product_performance(since),
        "emails": emails_collected(since),
        "recent_signups": recent_signups(),
        "errors": error_summary(since),
        "renewals": renewals(),
    }
