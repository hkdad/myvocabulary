from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.definition_fill_job import DefinitionFillJob

ACTIVE_JOB_STATUSES = ("queued", "running")
INTERRUPTED_MESSAGE = "Job interrupted — please start again."


async def fail_orphaned_definition_fill_jobs_in_session(db: AsyncSession) -> None:
    """Background fill tasks do not survive process restarts; clear stale active rows."""
    result = await db.execute(
        select(DefinitionFillJob).where(DefinitionFillJob.status.in_(ACTIVE_JOB_STATUSES))
    )
    jobs = list(result.scalars().all())
    if not jobs:
        return
    now = datetime.now(UTC)
    for job in jobs:
        job.status = "failed"
        job.error_message = INTERRUPTED_MESSAGE
        job.finished_at = now
    await db.commit()


async def fail_orphaned_definition_fill_jobs() -> None:
    async with AsyncSessionLocal() as db:
        await fail_orphaned_definition_fill_jobs_in_session(db)
