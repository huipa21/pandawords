from surrealdb import AsyncSurrealConnection, RecordID

from app.core.errors import AppError
from app.core.record_ids import decode_rid
from app.db import projects as repository
from app.domain.projects import ProjectCreate, ProjectPage, ProjectRead, ProjectUpdate


def _project_id(value: str) -> RecordID:
    try:
        return decode_rid(value, "project")
    except ValueError:
        raise AppError("project.not_found", 404, "Project not found.") from None


async def create_project(
    db: AsyncSurrealConnection, owner: str, data: ProjectCreate
) -> ProjectRead:
    return await repository.create_project(db, owner, data)


async def list_projects(
    db: AsyncSurrealConnection, owner: str, page: int, page_size: int
) -> ProjectPage:
    return await repository.list_projects(db, owner, page, page_size)


async def read_project(db: AsyncSurrealConnection, owner: str, id: str) -> ProjectRead:
    return await repository.read_project(db, owner, _project_id(id))


async def update_project(
    db: AsyncSurrealConnection, owner: str, id: str, data: ProjectUpdate
) -> ProjectRead:
    return await repository.update_project(db, owner, _project_id(id), data)


async def delete_project(db: AsyncSurrealConnection, owner: str, id: str) -> None:
    await repository.delete_project(db, owner, _project_id(id))
