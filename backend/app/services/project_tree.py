from surrealdb import AsyncSurrealConnection

from app.core.errors import AppError
from app.core.record_ids import decode_rid
from app.db import project_tree as repository
from app.domain.project_tree import ProjectMembershipRead, ProjectTreePage, TreeTable
from app.services.projects import _project_id


async def read_tree(
    db: AsyncSurrealConnection,
    owner: str,
    project_id: str,
    page: int,
    page_size: int,
    include_hidden: bool,
) -> ProjectTreePage:
    return await repository.read_tree(
        db, owner, _project_id(project_id), page, page_size, include_hidden
    )


async def set_visibility(
    db: AsyncSurrealConnection,
    owner: str,
    project_id: str,
    table: TreeTable,
    target_id: str,
    hidden: bool,
) -> ProjectMembershipRead:
    project = _project_id(project_id)
    try:
        target = decode_rid(target_id, table)
    except ValueError:
        raise AppError("project.item_not_found", 404, "Project item not found.") from None
    return await repository.set_visibility(db, owner, project, target, hidden)
