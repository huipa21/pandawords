from collections.abc import AsyncIterator
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import current_user, require_admin
from app.domain.auth import User


@pytest.fixture
async def auth_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    @app.get("/api/test-auth/user")
    async def protected(user: Annotated[User, Depends(current_user)]) -> dict[str, str]:
        return {"id": user.id, "role": user.role}

    @app.get("/api/test-auth/admin")
    async def admin(user: Annotated[User, Depends(require_admin)]) -> dict[str, str]:
        return {"id": user.id}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
