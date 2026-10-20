"""Optional desktop OAuth and Google APIs in an isolated JSON worker."""

from contextlib import redirect_stdout
import json
import sys
from urllib.parse import quote, urlparse

SCOPES = {
    "calendar": ["https://www.googleapis.com/auth/calendar.events.readonly"],
    "tasks": ["https://www.googleapis.com/auth/tasks"],
}


class PublicError(Exception):
    pass


def validate_client(data):
    client = data.get("installed")
    if not isinstance(client, dict):
        raise PublicError(
            "Choose a Google Desktop app OAuth client JSON, not a web/service-account key."
        )
    auth = urlparse(client.get("auth_uri", ""))
    if (
        auth.scheme != "https"
        or auth.hostname != "accounts.google.com"
        or auth.username
        or auth.password
        or client.get("token_uri") != "https://oauth2.googleapis.com/token"
    ):
        raise PublicError(
            "The OAuth client must use Google’s official authorization and token endpoints."
        )
    return client


def run(operation, data):
    if operation == "protocol_test":
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.oauth2.credentials import Credentials

        return {"ready": True}
    kind = data["kind"]
    if kind not in SCOPES:
        raise PublicError("Unknown Google integration.")
    if operation == "connect":
        from google_auth_oauthlib.flow import InstalledAppFlow

        with open(data["client_file"], encoding="utf-8") as stream:
            client = json.load(stream)
        validate_client(client)
        flow = InstalledAppFlow.from_client_config(
            client, SCOPES[kind], autogenerate_code_verifier=True
        )
        credentials = flow.run_local_server(
            host="127.0.0.1",
            port=0,
            open_browser=True,
            timeout_seconds=120,
            authorization_prompt_message="",
            success_message="Biscuit is connected. You can close this page.",
            access_type="offline",
            prompt="consent",
        )
        return {"credentials": json.loads(credentials.to_json()), "connected": True}
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request, AuthorizedSession

    info = data["credentials"]
    if info.get("token_uri") != "https://oauth2.googleapis.com/token":
        raise PublicError(
            "Stored Google credentials are invalid. Reconnect the account."
        )
    credentials = Credentials.from_authorized_user_info(info, SCOPES[kind])
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials.valid:
        raise PublicError(
            "Google authorization expired or was revoked. Reconnect the account."
        )
    session = AuthorizedSession(credentials, max_refresh_attempts=0)

    def request(method, url, body=None, etag=None, params=None):
        headers = {"If-Match": etag} if etag else {}
        response = session.request(
            method,
            url,
            json=body,
            params=params,
            headers=headers,
            timeout=20,
            allow_redirects=False,
            stream=True,
        )
        try:
            if response.status_code in (401, 403):
                raise PublicError(
                    "Google authorization expired or lacks permission. Reconnect the account."
                )
            if response.status_code == 412:
                raise PublicError(
                    "The cloud task changed. Refresh and resolve the conflict before writing."
                )
            if response.status_code == 429:
                raise PublicError(
                    "Google rate limit reached. Please wait and try again."
                )
            if not 200 <= response.status_code < 300:
                raise PublicError(
                    "Google could not complete the request. Refresh before retrying a task write."
                )
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > 2 * 1024 * 1024:
                    raise PublicError(
                        "Google response was too large. Choose a smaller list/date range."
                    )
            return json.loads(content) if content else {}
        finally:
            response.close()

    def pages(url, params):
        items = []
        for _ in range(10):
            page = request("GET", url, params=params)
            items.extend(page.get("items", []))
            if not page.get("nextPageToken"):
                return items, False
            params = dict(params, pageToken=page["nextPageToken"])
        return items, True

    try:
        root = "https://tasks.googleapis.com/tasks/v1"
        if operation == "task_lists":
            items, partial = pages(root + "/users/@me/lists", {"maxResults": 100})
            result = {"items": items, "partial": partial}
        elif operation == "tasks":
            url = root + "/lists/" + quote(data["list_id"], safe="") + "/tasks"
            items, partial = pages(
                url,
                {
                    "maxResults": 100,
                    "showCompleted": "true",
                    "showHidden": "false",
                    "showDeleted": "false",
                },
            )
            result = {"items": items, "partial": partial, "list_id": data["list_id"]}
        elif operation == "create_task":
            body = {"title": data["title"], "notes": data.get("description", "")}
            if data.get("due_at"):
                body["due"] = data["due_at"][:10] + "T00:00:00.000Z"
            item = request(
                "POST",
                root + "/lists/" + quote(data["list_id"], safe="") + "/tasks",
                body,
            )
            result = {
                "task": item,
                "list_id": data["list_id"],
                "local_id": data["local_id"],
            }
        elif operation == "complete_task":
            if not data.get("etag"):
                raise PublicError("Refresh the cloud task before marking it complete.")
            item = request(
                "PATCH",
                root
                + "/lists/"
                + quote(data["list_id"], safe="")
                + "/tasks/"
                + quote(data["external_id"], safe=""),
                {"status": "completed"},
                etag=data["etag"],
            )
            result = {
                "task": item,
                "list_id": data["list_id"],
                "local_id": data["local_id"],
            }
        elif operation == "calendar":
            items, partial = pages(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                {
                    "timeMin": data["time_min"],
                    "timeMax": data["time_max"],
                    "singleEvents": "true",
                    "orderBy": "startTime",
                    "maxResults": 250,
                },
            )
            result = {"items": items, "partial": partial}
        else:
            raise PublicError("Unsupported Google operation.")
        result["credentials"] = json.loads(credentials.to_json())
        return result
    finally:
        session.close()


def main():
    try:
        operation = sys.argv[1]
        data = json.loads(sys.stdin.buffer.read(2 * 1024 * 1024))
        with redirect_stdout(sys.stderr):
            result = run(operation, data)
        print(json.dumps({"ok": True, "result": result}))
    except ImportError:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "Optional Google packages are missing. Install the Google extra in the configured Python environment.",
                }
            )
        )
    except PublicError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
    except Exception:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "Google connection failed or authorization was cancelled. Check OAuth setup and reconnect; task writes are never retried automatically.",
                }
            )
        )


if __name__ == "__main__":
    main()
