"""Executable facts for SurrealDB 3.3.5 / Python SDK 3.0.0 (never the dev database)."""

from __future__ import annotations

from importlib.metadata import version
from urllib.parse import SplitResult, urlsplit, urlunsplit
from uuid import uuid4

import httpx
from surrealdb import AsyncSurreal
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from ..core.config import Settings
from .spike_graph import verify_graph
from .spike_operations import verify_operations
from .spike_records import verify_records
from .spike_support import Finding, first, schema


def spike_endpoint(url: str) -> SplitResult:
    endpoint = urlsplit(url)
    if endpoint.hostname not in {"localhost", "127.0.0.1", "::1"} or endpoint.port != 8101:
        raise ValueError("The spike requires the loopback test instance on port 8101")
    if (
        endpoint.scheme not in {"ws", "wss"}
        or endpoint.path != "/rpc"
        or endpoint.username is not None
        or endpoint.password is not None
        or endpoint.query
        or endpoint.fragment
    ):
        raise ValueError("The spike requires a credential-free WebSocket /rpc URL")
    if endpoint.hostname == "localhost":
        endpoint = endpoint._replace(netloc="127.0.0.1:8101")
    return endpoint


async def verify() -> None:
    settings = Settings()
    endpoint = spike_endpoint(settings.surreal_test_url)
    assert version("surrealdb") == "3.0.0", "This evidence targets SDK 3.0.0"
    base = urlunsplit(
        ("https" if endpoint.scheme == "wss" else "http", endpoint.netloc, "", "", "")
    )
    async with httpx.AsyncClient(base_url=base, timeout=5) as http:
        assert (await http.get("/health")).status_code == 200
        assert (await http.get("/version")).text == "surrealdb-3.3.5"
    findings = [Finding("N01", "PASS", "test /health=200; /version=surrealdb-3.3.5")]
    namespace = "spike_" + uuid4().hex
    database = "verify_" + uuid4().hex
    async with AsyncSurreal(urlunsplit(endpoint), timeout=10) as db:
        assert isinstance(db, AsyncWsSurrealConnection)
        await db.connect()
        await db.signin({"username": settings.surreal_user, "password": settings.surreal_pass})
        await db.use(namespace, database)
        assert await db.version() == "surrealdb-3.3.5"
        findings.append(
            Finding("N02", "PASS", "context manager/connect/signin/use/version succeeded")
        )
        try:
            await schema(db)
            results = await db.query("RETURN $text; RETURN 2;", {"text": "run"})
            assert results == ["run", 2], results
            assert await db.query("RETURN 1;").first() == 1
            selected = await first(
                db, "SELECT * FROM lemma WHERE owner = NONE AND text = $text;", {"text": "run"}
            )
            assert selected == []
            raw = await db.query_raw("RETURN 1;")
            assert raw["result"][0]["status"] == "OK"
            try:
                await db.query("THROW 'spike_query_error';")
            except Exception as error:
                assert "spike_query_error" in str(error)
            else:
                raise AssertionError("query must not silently ignore a statement error")
            findings.append(
                Finding("N03", "PASS", "query => one result/statement; SELECT nested rows")
            )
            findings.extend(await verify_records(db))
            findings.extend(await verify_graph(db))
            findings.extend(await verify_operations(db, namespace, database))
        finally:
            # Only these two generated databases can ever be removed, even after a failed assertion.
            await db.use(namespace, database)
            for name in (database + "_restore", database):
                await db.query("REMOVE DATABASE IF EXISTS $database;", {"database": name})
            assert not (await first(db, "INFO FOR NS;"))["databases"]
    for finding in findings:
        print(f"{finding.note} {finding.status}: {finding.evidence}")
    assert len(findings) == 23
    print("23/23 verified; generated databases removed; shared server left running.")
