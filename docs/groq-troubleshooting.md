# Groq connection investigation

## Evidence and scope

The reported base URL, `https://api.groq.com/openai/v1`, matches the official Groq preset. The reported model is `openai/gpt-oss-20b`; availability for the user's key must be checked through the authenticated model list and a chat completion.

Before this fix, `Companion._finished()` produced “The provider rejected access. Check your API key and model permissions.” only for **HTTP 401 or 403**. It discarded the distinction and the provider error code. The report therefore establishes an access rejection, but does not establish which of these two statuses occurred or its underlying account/network cause. A request appearing in GroqCloud does not establish successful authorization or a completed reply.

Inspection also found a reproducible credential defect: Groq → Offline → Custom could place the current Groq session key in Custom's field, and Custom could inherit the previous provider's URL when no Custom profile existed. Both paths now restore the selected provider's own credentials and connection. The user's report does not establish that this switching sequence occurred.

No Groq key or authenticated Windows session was available in the cloud workspace. The user's live `/models` permissions and chat response remain unverified. The new tests use a local HTTP server and dummy keys.

## Changes

- Shared validation and request construction in `desktop_pet/ai_protocol.py`. The Groq preset requires its exact canonical endpoint. Keys are checked for invalid whitespace/control characters and sent as `Authorization: Bearer <key>`.
- Groq uses `max_completion_tokens`, as preferred by the [official client schema](https://github.com/groq/groq-python/blob/main/src/groq/types/chat/completion_create_params.py). Custom/Ollama retain `max_tokens`. Sampling remains configurable; no model-specific overrides are guessed. This is a compatibility improvement; the underlying access rejection still requires the new diagnostic result.
- Discovery and chat use matching JSON headers and an explicit Biscuit User-Agent. These headers are not evidence of the original failure's cause.
- Custom, Groq, and Ollama retain separate OS credential accounts (`api-key`, `api-key-groq`, `api-key-ollama`). Switching providers reloads the correct account; unavailable Groq credentials never fall back to Custom. No credentials go into preferences or logs.
- Test / models optionally verifies a minimal chat completion after checking the selected model is listed. It sends only `Reply with OK.`, using the configured Reply tokens/Creativity limits, without earlier chat. The opt-in checkbox states that the request uses provider quota. Tests never automatically retry chat.
- Editing the connection or switching providers cancels pending tests. A changed host requires re-entering its key before either discovery or saving. Conversation history and offline fallback remain intact.

## Safe diagnostic messages

| Response | Displayed classification and action |
| --- | --- |
| 400 / 422 | Invalid chat request; review model parameters. A recognized parameter name is included when supplied. |
| 401 | Authentication failed; re-enter the selected provider's key. |
| 403 | Access forbidden; review organization/model permissions and network/region policy. |
| 404 | Endpoint/model not found; known model errors direct the user to discovery. |
| 429 | Rate/quota exceeded; respect the cooldown and check account limits. |
| 5xx | Provider unavailable; retry later or use offline chat. |
| 200 with empty text and `finish_reason=length` | Increase Reply tokens for the reasoning model. |

Only HTTP status and allowlisted error code/type/parameter identifiers are displayed. Error messages are local, fixed descriptions. Arbitrary provider messages, unknown IDs, HTML, headers, URLs, keys, and conversation content are never echoed as diagnostics. A successful model list explicitly says chat has not been tested.

## Verification results

- **240 tests passed**, including 38 new Groq checks. These exercise actual Qt requests to a local mock HTTP server: 400/401/403/404/429/503 for model discovery, normal chat, and the model-then-chat probe; successful discovery/chat; key persistence/reload and Authorization headers; missing-key handling; provider switching/cancellation; private error fields; and reasoning-token exhaustion.
- The source application's native offscreen startup smoke test passed. Import/unused-code checks and `git diff --check` passed.
- An initial full run caught a settings regression introduced during this change (enabling AI restored a saved model over an unfinished edit). It was corrected before the final 240-test run. Existing settings, offline fallback, animations, activities, compact UI, and lifecycle tests remain passing.
- No dependency changes, executable builds, live Groq calls, or Windows acceptance tests were performed for this fix. Live account verification requires the user's configured key and the new connection test.

## Steps for this configuration

1. Select **Groq — cloud AI** in Preferences. Keep `https://api.groq.com/openai/v1` and enter the Groq key in that provider's key field. Paste only the key, without `Bearer`.
2. Click **Test / models**. Select `openai/gpt-oss-20b` only if returned by the authenticated list; otherwise select an available model or review Groq project/model permissions.
3. Enable **Include minimal chat test**, then click **Test / models** again. Success requires a received chat reply, not just a model list. If the result is HTTP 200 with token exhaustion, increase Reply tokens (for example to 1024) and repeat; the test consumes quota.
4. Save the AI connection. If access still fails, the displayed phase, HTTP status, and recognized error code identify the next account/network check. Share only that sanitized status if further investigation is needed. Never share the key or Authorization header.

Run source verification with `python -m pytest -q` and `python run_pet.py --smoke-test` (use `QT_QPA_PLATFORM=offscreen` on headless Linux). Native Windows, live account permissions, and the user's installed executable require their own acceptance checks. This change edits the existing source; no application package is rebuilt.
