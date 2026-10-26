import re
from uuid import uuid4

_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,128}")


class RequestIdMiddleware:
    def __init__(self, app: object) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: object, send: object) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)  # type: ignore[operator]
            return

        request_id = _request_id_from_scope(scope)

        async def send_with_request_id(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)  # type: ignore[operator]

        await self.app(scope, receive, send_with_request_id)  # type: ignore[operator]


def _request_id_from_scope(scope: dict) -> str:
    for key, value in scope.get("headers", []):
        if key.lower() != b"x-request-id":
            continue
        try:
            candidate = value.decode("ascii")
        except UnicodeDecodeError:
            break
        if _REQUEST_ID_PATTERN.fullmatch(candidate):
            return candidate
        break
    return str(uuid4())
