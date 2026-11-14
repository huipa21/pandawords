from http.cookies import SimpleCookie

from httpx import AsyncClient, Response

PASSWORD = "test-password-123"
NEW_PASSWORD = "new-pass45"
COOKIE = "refresh_token"


async def login(client: AsyncClient, username: str, password: str = PASSWORD) -> Response:
    return await client.post("/api/auth/login", json={"username": username, "password": password})


def bearer(response: Response) -> dict[str, str]:
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def refresh_cookie(response: Response) -> str:
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie[COOKIE].value


def cookie_header(token: str) -> dict[str, str]:
    return {"Cookie": f"{COOKIE}={token}"}


def assert_invalid(response: Response) -> None:
    assert response.status_code == 401, response.text
    assert response.json() == {
        "code": "auth.invalid_credentials",
        "message": "Invalid credentials.",
        "field": None,
    }


def assert_gate(response: Response) -> None:
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "auth.password_change_required"


def assert_cookie_deleted(response: Response) -> None:
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    assert cookie[COOKIE].value == ""
    assert cookie[COOKIE]["max-age"] == "0"
    assert cookie[COOKIE]["path"] == "/api/auth"
