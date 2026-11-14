from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import Db, current_user
from app.domain.auth import User
from app.domain.graph import GraphNode, GraphQuery, GraphRead, GraphSeedsQuery
from app.services import graph

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("/seeds")
async def graph_seeds(
    query: Annotated[GraphSeedsQuery, Query()],
    db: Db,
    actor: Annotated[User, Depends(current_user)],
    response: Response,
) -> list[GraphNode]:
    response.headers["Cache-Control"] = "no-store"
    return await graph.seeds(db, actor.id, query)


@router.get("")
async def read_graph(
    query: Annotated[GraphQuery, Query()],
    db: Db,
    actor: Annotated[User, Depends(current_user)],
    response: Response,
) -> GraphRead:
    response.headers["Cache-Control"] = "no-store"
    return await graph.read(db, actor.id, query)
