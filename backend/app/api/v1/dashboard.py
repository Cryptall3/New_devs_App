from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, Optional
from app.services.cache import get_revenue_summary
from app.services.reservations import PropertyNotFound
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    # Tenant always comes from the authenticated user's token. Never from
    # client-supplied headers or query parameters.
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated with this account")

    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, month=month, year=year)
    except PropertyNotFound:
        # 404 rather than 403: it must not confirm that another tenant owns
        # this property ID.
        raise HTTPException(status_code=404, detail="Property not found")

    total_revenue_float = float(revenue_data['total'])
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": total_revenue_float,
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count'],
        "month": revenue_data.get('month'),
        "year": revenue_data.get('year'),
    }
