from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict
from zoneinfo import ZoneInfo

MONEY_QUANT = Decimal("0.01")


class PropertyNotFound(Exception):
    """Raised when a property does not exist for the requesting tenant."""


def _to_money(value: Decimal) -> Decimal:
    """Round a currency amount once, half-up, at the very end of the calculation."""
    return Decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _month_bounds_local(year: int, month: int, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Return the instants bounding a calendar month in the property's timezone."""
    local_start = datetime(year, month, 1, tzinfo=tz)
    if month < 12:
        local_end = datetime(year, month + 1, 1, tzinfo=tz)
    else:
        local_end = datetime(year + 1, 1, 1, tzinfo=tz)
    return local_start, local_end


async def _get_property(session, property_id: str, tenant_id: str):
    """
    Fetch a property scoped to the tenant.

    Returns None when the property does not exist for that tenant, which lets
    callers tell "this property is not yours" apart from "no bookings yet".
    """
    from sqlalchemy import text

    result = await session.execute(
        text("SELECT timezone FROM properties WHERE id = :property_id AND tenant_id = :tenant_id"),
        {"property_id": property_id, "tenant_id": tenant_id},
    )
    return result.fetchone()


async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
    month: int | None = None,
    year: int | None = None,
) -> Dict[str, Any]:
    """
    Aggregate revenue for a calendar month in the property's local timezone.

    Defaults to the most recent month that has bookings for this property.
    Raises PropertyNotFound when the property is not owned by the tenant.
    """
    from app.core.database_pool import db_pool
    from sqlalchemy import text

    await db_pool.initialize()
    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")

    async with db_pool.get_session() as session:
        property_row = await _get_property(session, property_id, tenant_id)
        if not property_row:
            # Do not reveal whether the property exists for another tenant.
            raise PropertyNotFound(property_id)

        timezone_name = property_row.timezone or "UTC"
        try:
            property_tz = ZoneInfo(timezone_name)
        except Exception:
            property_tz = ZoneInfo("UTC")

        # Group the requested month in the property's local time, not in UTC.
        if month and year:
            target_year, target_month = year, month
        else:
            latest = await session.execute(
                text("""
                    SELECT check_in_date
                    FROM reservations
                    WHERE property_id = :property_id AND tenant_id = :tenant_id
                    ORDER BY check_in_date DESC
                    LIMIT 1
                """),
                {"property_id": property_id, "tenant_id": tenant_id},
            )
            latest_row = latest.fetchone()
            if latest_row and latest_row.check_in_date:
                local = latest_row.check_in_date.astimezone(property_tz)
                target_year, target_month = local.year, local.month
            else:
                now_local = datetime.now(property_tz)
                target_year, target_month = now_local.year, now_local.month

        start_local, end_local = _month_bounds_local(target_year, target_month, property_tz)

        query = text("""
            SELECT
                COALESCE(SUM(total_amount), 0) AS total_revenue,
                COUNT(*) AS reservation_count
            FROM reservations
            WHERE property_id = :property_id
              AND tenant_id = :tenant_id
              AND check_in_date >= :start_date
              AND check_in_date < :end_date
        """)

        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_local,
            "end_date": end_local,
        })
        row = result.fetchone()

        raw_total = row.total_revenue if row else Decimal("0")
        reservation_count = row.reservation_count if row else 0

        # NUMERIC(10, 3) arrives as Decimal; keep full precision and round once.
        total_revenue = _to_money(Decimal(raw_total))

        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": str(total_revenue),
            "currency": "USD",
            "count": reservation_count,
            "month": target_month,
            "year": target_year,
            "timezone": timezone_name,
        }
