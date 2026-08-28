import pytest
from sqlalchemy import select

from app.models.definition_fill_job import DefinitionFillJob
from app.models.user import User
from app.startup import INTERRUPTED_MESSAGE, fail_orphaned_definition_fill_jobs_in_session


@pytest.mark.asyncio
async def test_fail_orphaned_definition_fill_jobs_marks_active_rows_failed(db_session) -> None:
    parent = (await db_session.execute(select(User).where(User.username == "parent"))).scalar_one()
    job = DefinitionFillJob(
        parent_id=parent.id,
        scope="books",
        status="running",
        total=10,
        processed=2,
    )
    db_session.add(job)
    await db_session.commit()

    await fail_orphaned_definition_fill_jobs_in_session(db_session)

    refreshed = (
        await db_session.execute(select(DefinitionFillJob).where(DefinitionFillJob.id == job.id))
    ).scalar_one()
    assert refreshed.status == "failed"
    assert refreshed.error_message == INTERRUPTED_MESSAGE
    assert refreshed.finished_at is not None


@pytest.mark.asyncio
async def test_fail_orphaned_definition_fill_jobs_leaves_completed_rows(db_session) -> None:
    parent = (await db_session.execute(select(User).where(User.username == "parent"))).scalar_one()
    job = DefinitionFillJob(
        parent_id=parent.id,
        scope="books",
        status="completed",
        total=5,
        processed=5,
    )
    db_session.add(job)
    await db_session.commit()

    await fail_orphaned_definition_fill_jobs_in_session(db_session)

    refreshed = (
        await db_session.execute(select(DefinitionFillJob).where(DefinitionFillJob.id == job.id))
    ).scalar_one()
    assert refreshed.status == "completed"
