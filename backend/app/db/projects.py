"""Owner-scoped project persistence and atomic membership cleanup."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from surrealdb import AsyncSurrealConnection, RecordID
from surrealdb.types import Value

from app.core.errors import AppError
from app.core.record_ids import encode_rid
from app.db.auth import _atomic, _rows
from app.domain.identity import user_key
from app.domain.projects import ProjectCreate, ProjectPage, ProjectRead, ProjectUpdate


def _read(row: dict[str, Any]) -> ProjectRead:
    return ProjectRead.model_validate({**row, "id": encode_rid(row["id"], "project")})


def _not_found() -> AppError:
    return AppError("project.not_found", 404, "Project not found.")


async def create_project(
    db: AsyncSurrealConnection, owner: str, data: ProjectCreate
) -> ProjectRead:
    content: dict[str, Value] = {
        **data.model_dump(),
        "owner": RecordID("user", user_key(owner)),
        "created_at": datetime.now(UTC),
    }
    rows = await _rows(
        db,
        "CREATE $project CONTENT $content RETURN AFTER;",
        {"project": RecordID("project", uuid4().hex), "content": content},
    )
    return _read(rows[0])


async def list_projects(
    db: AsyncSurrealConnection, owner: str, page: int, page_size: int
) -> ProjectPage:
    async def operation(txn: UUID) -> ProjectPage:
        user = RecordID("user", user_key(owner))
        rows = await _rows(
            db,
            "SELECT * FROM project WHERE owner = $user ORDER BY created_at DESC, id "
            "LIMIT $limit START $start;",
            {"user": user, "limit": page_size, "start": (page - 1) * page_size},
            txn_id=txn,
        )
        counts = await _rows(
            db,
            "SELECT count() AS total FROM project WHERE owner = $user GROUP ALL;",
            {"user": user},
            txn_id=txn,
        )
        return ProjectPage(
            items=[_read(row) for row in rows],
            total=counts[0]["total"] if counts else 0,
            page=page,
            page_size=page_size,
        )

    return await _atomic(db, operation)


async def read_project(db: AsyncSurrealConnection, owner: str, project: RecordID) -> ProjectRead:
    rows = await _rows(
        db,
        "SELECT * FROM $project WHERE owner = $user;",
        {"project": project, "user": RecordID("user", user_key(owner))},
    )
    if not rows:
        raise _not_found()
    return _read(rows[0])


async def update_project(
    db: AsyncSurrealConnection, owner: str, project: RecordID, data: ProjectUpdate
) -> ProjectRead:
    rows = await _rows(
        db,
        "UPDATE $project MERGE $changes WHERE owner = $user RETURN AFTER;",
        {
            "project": project,
            "user": RecordID("user", user_key(owner)),
            "changes": data.model_dump(include=data.model_fields_set),
        },
    )
    if not rows:
        raise _not_found()
    return _read(rows[0])


async def delete_project(db: AsyncSurrealConnection, owner: str, project: RecordID) -> None:
    async def operation(txn: UUID) -> None:
        parameters: dict[str, Value] = {
            "project": project,
            "user": RecordID("user", user_key(owner)),
        }
        rows = await _rows(
            db,
            "SELECT * FROM $project WHERE owner = $user;",
            parameters,
            txn_id=txn,
        )
        if not rows:
            raise _not_found()
        # SurrealDB also deletes connected relations when their endpoint is deleted.
        foreign = await _rows(
            db,
            "SELECT id FROM includes WHERE in = $project AND in.owner = $user "
            "AND owner != $user LIMIT 1;",
            parameters,
            txn_id=txn,
        )
        if foreign:
            raise AppError(
                "project.membership_conflict", 409, "Project has inconsistent membership ownership."
            )
        await _rows(
            db,
            "DELETE includes WHERE in = $project AND owner = $user;",
            parameters,
            txn_id=txn,
        )
        deleted = await _rows(
            db,
            "DELETE $project WHERE owner = $user RETURN BEFORE;",
            parameters,
            txn_id=txn,
        )
        if not deleted:
            raise _not_found()

    await _atomic(db, operation)
