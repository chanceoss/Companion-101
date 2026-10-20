"""Shared AI request contract and allowlisted, privacy-safe error descriptions."""

import json
from urllib.parse import urlparse

from PySide6.QtNetwork import QNetworkRequest

GROQ_ENDPOINT = "https://api.groq.com/openai/v1"
AI_HEADERS = {
    b"Accept": b"application/json",
    b"User-Agent": b"BiscuitCompanion/1.1 (OpenAI-compatible client)",
}


def validate_endpoint(base):
    try:
        parsed = urlparse(base.strip())
        hostname = parsed.hostname
        _ = parsed.port
    except (ValueError, AttributeError):
        raise ValueError(
            "Enter a valid API address and port without embedded credentials."
        ) from None
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and hostname in ("localhost", "127.0.0.1", "::1")
    ):
        raise ValueError(
            "Use an HTTPS API address, or HTTP for a local model on localhost."
        )
    if (
        not hostname
        or any(c.isspace() for c in hostname)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Enter a base API URL without credentials, query parameters, or fragments."
        )


def validate_key(key):
    if any(ord(c) < 32 or ord(c) > 126 for c in key):
        raise ValueError(
            "The API key must be one line of plain text without control characters."
        )
    key = key.strip()
    if any(c.isspace() for c in key) or key.lower().startswith("bearer "):
        raise ValueError(
            "Paste only the API key value, without a Bearer prefix or spaces."
        )
    return key


def validate_connection(selected, endpoint, key):
    validate_endpoint(endpoint)
    key = validate_key(key)
    if selected == "groq":
        if endpoint.rstrip("/") != GROQ_ENDPOINT:
            raise ValueError(
                "Groq requires https://api.groq.com/openai/v1. Choose Custom for another endpoint."
            )
        if not key:
            raise ValueError(
                "No Groq API key is loaded. Enter your Groq key in Preferences; it is stored separately from Custom and Ollama."
            )
    if selected == "ollama" and urlparse(endpoint).hostname not in (
        "localhost",
        "127.0.0.1",
        "::1",
    ):
        raise ValueError(
            "Use a localhost/loopback endpoint for Ollama. Choose Custom for a remote HTTPS server."
        )
    return key


def apply_ai_headers(request, key):
    request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
    for name, value in AI_HEADERS.items():
        request.setRawHeader(name, value)
    if key:
        request.setRawHeader(b"Authorization", ("Bearer " + key).encode("ascii"))


def chat_payload(selected, model, messages, max_tokens, temperature):
    payload = {
        "model": model,
        "messages": messages,
        "max_completion_tokens" if selected == "groq" else "max_tokens": max_tokens,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    return payload


def chat_text(data):
    try:
        choice = data["choices"][0]
        content = choice["message"]["content"]
        if isinstance(content, str) and content.strip():
            return content
        if choice.get("finish_reason") == "length":
            raise ValueError(
                "HTTP 200: the reply token limit was reached before any text was returned. Increase Reply tokens, especially for reasoning models such as GPT-OSS."
            )
    except (KeyError, IndexError, TypeError):
        pass
    raise ValueError(
        "The provider returned an unsupported chat response. Use an OpenAI-compatible chat completions API."
    )


# Never echo arbitrary code/type/param/message fields. A provider can repeat a key
# or a private prompt in any of them, including strings that look like safe IDs.
ERROR_CODES = {
    "invalid_api_key": "auth",
    "invalid_authentication": "auth",
    "authentication_error": "auth",
    "permission_denied": "permission",
    "permission_error": "permission",
    "model_permission_blocked": "permission",
    "organization_restricted": "permission",
    "access_denied": "permission",
    "unsupported_country_region_territory": "region",
    "model_not_found": "model",
    "model_decommissioned": "model",
    "invalid_model": "model",
    "invalid_request_error": "request",
    "invalid_request": "request",
    "invalid_value": "request",
    "unsupported_parameter": "request",
    "unsupported_value": "request",
    "context_length_exceeded": "context",
    "rate_limit_exceeded": "rate",
    "rate_limit_error": "rate",
    "insufficient_quota": "quota",
    "billing_hard_limit_reached": "quota",
    "server_error": "server",
    "service_unavailable": "server",
}
PARAMETERS = {
    "model",
    "messages",
    "temperature",
    "max_tokens",
    "max_completion_tokens",
    "reasoning_effort",
    "top_p",
    "stream",
    "n",
}


def provider_error(status, body=b""):
    """Describe a bounded response using static text, HTTP status, and known IDs."""
    error = {}
    try:
        data = json.loads(body[:65536])
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            error = data["error"]
    except (ValueError, TypeError, UnicodeError):
        pass
    code = next(
        (
            error.get(field)
            for field in ("code", "type")
            if isinstance(error.get(field), str) and error[field] in ERROR_CODES
        ),
        None,
    )
    kind = ERROR_CODES.get(code)
    if status == 401:
        kind = "auth"
    elif status == 429:
        kind = "quota" if kind == "quota" else "rate"
    elif status == 403 and kind not in ("permission", "region"):
        kind = "permission"
    messages = {
        "auth": "Authentication failed: the provider rejected access with this API key. Re-enter the key for the selected provider and save the AI connection.",
        "permission": "Access forbidden. Check organization/model permissions and network or region restrictions; try the authenticated model and chat tests in Preferences.",
        "region": "Access is restricted by the provider's country or region policy. Check your account and network location with the provider.",
        "model": "The selected model is unavailable, retired, or inaccessible to this key. Discover models and select an exact ID from the authenticated list.",
        "request": "Invalid chat request. Check the selected model and its supported parameters in Preferences.",
        "context": "The conversation exceeds the model's context limit. Clear the conversation or select a model with a larger context window.",
        "rate": "The provider rate limit or quota was reached. Wait before trying again; check your provider limits.",
        "quota": "The provider account quota was reached. Check the account's usage and billing limits or choose local/offline chat.",
        "server": "The provider service is unavailable. Try again later or choose offline chat.",
    }
    if kind in messages:
        reason = messages[kind]
    elif status == 400 or status == 422:
        reason = messages["request"]
    elif status == 404:
        reason = "The API endpoint or model was not found. Check the base URL and discover available models in Preferences."
    elif isinstance(status, int) and 300 <= status < 400:
        reason = "The provider redirected the request. Redirects are blocked; check the API base URL."
    elif isinstance(status, int) and status >= 500:
        reason = messages["server"]
    elif status:
        reason = "The provider rejected the request. Check the connection and account configuration."
    else:
        reason = "The server could not be reached or the request timed out. Check connectivity and TLS/network policy."
    prefix = (
        f"HTTP {status}"
        if isinstance(status, int) and 100 <= status <= 599
        else "Connection failed"
    )
    if code:
        prefix += f" · {code}"
    param = error.get("param")
    if kind == "request" or status in (400, 422):
        if isinstance(param, str) and param in PARAMETERS:
            reason += f" Parameter: {param}."
    return prefix + ": " + reason
