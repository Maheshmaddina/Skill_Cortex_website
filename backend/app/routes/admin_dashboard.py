from fastapi import APIRouter, Depends

from app.dependencies import DbSession, require_admin
from app.schemas.admin import DashboardStats
from app.services.dashboard import dashboard_stats

router = APIRouter(prefix="/admin/dashboard", tags=["admin: dashboard"], dependencies=[Depends(require_admin)])


@router.get("/stats", response_model=DashboardStats)
def get_stats(db: DbSession) -> DashboardStats:
    """Headline numbers for the admin dashboard. Revenue counts PAID payments only (refunds excluded)."""
    return DashboardStats.model_validate(dashboard_stats(db))
