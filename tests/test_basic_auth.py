import httpx

from owl.auth import Settings, SungrowAuthenticator


def test_basic_auth_response_code_is_200() -> None:
    settings = Settings(
        base_url="https://example.test/service",
        login_path="/security/auth/login",
        username="xxxx",
        password="xxxx",
        timeout=5,
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 200, "data": {"token": "token-123"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        token = SungrowAuthenticator(settings).login(client=client)

    assert token == "token-123"
