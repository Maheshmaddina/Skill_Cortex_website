"""Endpoints for the platform itself, not for learners or admins."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from app.config import get_settings
from app.scheduler import jobs

router = APIRouter(prefix="/internal", tags=["internal"])


@router.api_route("/run-jobs", methods=["GET", "POST"])
def run_jobs(authorization: Annotated[str | None, Header()] = None) -> dict[str, str]:
    """Run every background job once. Needs `Authorization: Bearer <CRON_SECRET>`.

    Used where the scheduler process can't run (Vercel): Vercel Cron and the scheduled GitHub
    Actions workflow call this. Safe to call concurrently or repeatedly.
    """
    secret = get_settings().cron_secret
    if not secret or not hmac.compare_digest(authorization or "", f"Bearer {secret}"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    return jobs.run_due_jobs()
