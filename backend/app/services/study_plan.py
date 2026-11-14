"""Project study queues and a deduplicated owner dashboard."""

from datetime import datetime
from uuid import UUID

from surrealdb import AsyncSurrealConnection

from app.db import study_plan as repository
from app.db.auth import _atomic
from app.domain.study_plan import (
    DashboardRead,
    ProjectForecast,
    SenseOrderRead,
    SenseOrderUpdate,
    StudyPlanRead,
)
from app.services import srs
from app.services.projects import read_project
from app.services.study_plan_calculations import (
    available_new_count,
    completed_counts,
    exam_pacing,
    forecast,
    history_statistics,
    queue,
    utc_now,
)


async def read_plan(
    db: AsyncSurrealConnection,
    owner: str,
    project_id: str,
    *,
    offset: int = 0,
    limit: int = 100,
    now: datetime | None = None,
) -> StudyPlanRead:
    project = srs._decode(project_id, "project")
    # Authorize before reconciling legacy selections.
    await read_project(db, owner, project_id)
    await srs.reconcile_memberships(db, owner)
    at = utc_now(now)

    async def operation(txn: UUID) -> StudyPlanRead:
        snapshot = await repository.snapshot(db, owner, project, txn)
        logs = await repository.history(db, owner, at, txn)
        today = completed_counts(logs, at, project_id)
        plan, cards = snapshot.project.plan, snapshot.cards
        items = queue(cards, plan, today, at)
        new = sum(not card.introduced for card in cards)
        return StudyPlanRead(
            project_id=project_id,
            as_of=at,
            plan=plan,
            due=sum(card.introduced and card.card.due <= at for card in cards),
            new=new,
            today=today,
            remaining_new_allowance=max(0, plan.daily_new - today.new),
            remaining_review_allowance=(
                max(0, plan.review_cap - today.reviews) if plan.review_cap is not None else None
            ),
            queue=items[offset : offset + limit],
            queue_total=len(items),
            offset=offset,
            limit=limit,
            exam=exam_pacing(plan, new, today.new, at),
            forecast=forecast(cards, at),
        )

    return await _atomic(db, operation)


async def reorder(
    db: AsyncSurrealConnection, owner: str, project_id: str, data: SenseOrderUpdate
) -> SenseOrderRead:
    project = srs._decode(project_id, "project")
    senses = [srs._decode(value, "sense") for value in data.sense_ids]

    async def operation(txn: UUID) -> SenseOrderRead:
        result = await repository.reorder(db, owner, project, senses, txn)
        return SenseOrderRead(project_id=project_id, sense_ids=result)

    return await _atomic(db, operation)


async def read_dashboard(
    db: AsyncSurrealConnection, owner: str, *, now: datetime | None = None
) -> DashboardRead:
    at = utc_now(now)
    await srs.reconcile_memberships(db, owner)

    async def operation(txn: UUID) -> DashboardRead:
        logs = await repository.history(db, owner, at, txn)
        cards = {}
        allowances = []
        projects = []
        for project in await repository.project_ids(db, owner, txn):
            snapshot = await repository.snapshot(db, owner, project, txn)
            record = snapshot.project
            today = completed_counts(logs, at, record.id)
            new = sum(not card.introduced for card in snapshot.cards)
            projected = forecast(snapshot.cards, at)
            projects.append(
                ProjectForecast(
                    project_id=record.id,
                    name=record.name,
                    due=projected[0].due,
                    new=new,
                    today=today,
                    forecast=projected,
                    exam=exam_pacing(record.plan, new, today.new, at),
                )
            )
            cards.update({card.id: card for card in snapshot.cards})
            allowances.append((snapshot.cards, max(0, record.plan.daily_new - today.new)))
        retention, streak = history_statistics(logs, at)
        projected = forecast(list(cards.values()), at)
        return DashboardRead(
            as_of=at,
            due_today=projected[0].due,
            new_today=available_new_count(allowances),
            today=completed_counts(logs, at),
            retention_30_days=retention,
            streak=streak,
            forecast=projected,
            projects=projects,
        )

    return await _atomic(db, operation)
