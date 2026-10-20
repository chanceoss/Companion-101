# Biscuit 1.1 smart companion upgrade report

Implemented in the existing native PySide6 application on 2026-10-20. No browser app, replacement pet, new screenshot capture, desktop automation, or unrelated repository changes were introduced. Existing artwork, animation engine, activities, focus timer, dragging/clicks, tray, startup, custom provider settings, and legacy credential entry remain compatible.

## Completed implementation phases

| Phase | Delivered | Full-suite result |
| --- | --- | --- |
| Baseline | Existing desktop companion verified before edits | 143 passed |
| 1 | Ollama/Groq/custom selection, model discovery, secure profiles, explicit context reuse, safe offline fallback, limits | 149 passed |
| 2 | Opt-in Open-Meteo forecasts/geocoding/cache and read-only system/battery indicators | 153 passed |
| 3 | Local Piper speech, explicit memory-only microphone capture, editable Faster Whisper transcription, approved downloads | 159 passed |
| 4 | Migrated SQLite reminders/tasks, deterministic timezone scheduling, Google desktop OAuth, read-only Calendar, confirmed Tasks writes and conflict handling | 175 passed |
| 5 | Optional Open Trivia DB, offline questions/daily challenge, difficulty, scores, reactions | 179 passed |
| 6 | Lifecycle/privacy hardening, corrupted data recovery, compact settings/tools, release packaging, documentation | 202 passed |

Each implementation phase is a separate commit. Tests that failed during implementation were corrected before publication; no failing tests remain in the final run.

## Validation performed

- 202 automated tests passed. Real local mock HTTP requests verify asynchronous transport, rate limits, bounded retries with exponential backoff, cancellation, redirects, model discovery, context isolation, and fallback.
- Native Qt screenshots were rendered and inspected. The full compact control panel fits 480 × 540 with Work, voice status, and error controls; Preferences fits 460 × 500 across all sections.
- SQLite persistence/migrations, timezone/DST handling, once-only reminder delivery, task deduplication/conflicts, cancelled cloud writes, score persistence, and settings recovery are tested.
- OAuth scopes/PKCE/secure storage and task confirmation/ETag handling are tested with mocks. Model processing is tested with mocked Piper/Whisper backends; audio conversion uses real NumPy test data.
- Startup succeeds with every optional backend import intentionally unavailable. Shutdown stops timers, captures, network replies, and worker processes even when preference saving fails.
- The 1.1 wheel builds and passes an isolated native Qt smoke test. A Linux PyInstaller package builds and passes native startup and both bundled JSON-worker protocol checks. These are Linux checks, not Windows release validation.
- The Windows build script/workflow include the small optional integrations, timezone data, Qt Multimedia, worker assets, and packaged-worker tests. Speech libraries and models are deliberately kept in a separate optional environment.

## Dependencies and APIs

Core additions: tzdata 2026.5. Existing PySide6 6.8.3 and keyring 25.6.0 remain. Small optional build integrations: psutil 7.2.2, google-auth 2.62.0, google-auth-oauthlib 1.5.0, requests 2.34.2. Dev tests add NumPy 2.2.6. Optional external voice requirements are Piper, Faster Whisper, and Hugging Face Hub; no speech model or large AI model was downloaded for this work.

APIs implemented: Ollama/OpenAI-compatible model and chat endpoints; Groq compatible model/chat endpoints; Open-Meteo geocoding and forecasts; Google desktop OAuth, Tasks REST, and read-only primary Calendar events; Open Trivia Database. Local features use SQLite, Qt Multimedia, psutil, and a Windows power-status fallback.

## Setup, limits, and remaining verification

- Built-in replies, local reminders/tasks, offline trivia, and existing animations require no account or paid subscription. All remote integrations start disabled.
- Ollama needs an installed/running server and a user-selected model. Groq/custom cloud AI needs the user's endpoint/model/key. Keys stay in memory or the OS keyring; no credentials were committed.
- Voice needs the user's speech environment, local voice/recognition models, and working input/output devices. Downloads require confirmation. Actual Piper/Whisper inference, real microphone capture, and speaker playback were not available for live testing here.
- Google needs the user's Cloud project, enabled APIs, Desktop OAuth client JSON, explicit account grant, and working secure credential storage. No live account/client was supplied; live authorization, revoked grants, and real account synchronization remain acceptance checks.
- Several provider documentation/API hosts are blocked by the workspace proxy. Accessible official repositories/SDK interfaces and licenses were reviewed, but current numeric pricing/free-tier quotas could not all be verified. The setup guide links official terms and does not promise unlimited free usage. Open-Meteo's free public service is non-commercial; Piper and individual voices have separate licensing obligations.
- Windows tray/transparency/DPI/multiple monitors, Credential Manager, logon startup, audio permission behavior, and the Windows executable still require native Windows acceptance testing. The supplied workflow provides automated Windows checks after publication.
- Implemented service adapters are real code, not live-configured accounts or bundled models. Calendar writes, cloud task deletion, process control, global keyboard hooks, and continuous/background microphone recording are intentionally absent.

See [integration setup and troubleshooting](integrations.md), [README](../README.md), and the updated [voice settings](preferences-voice.png) / [mini games](tools.png) captures.

## Files created (39)

- [desktop_pet/assets/google_worker.py](../desktop_pet/assets/google_worker.py)
- [desktop_pet/assets/voice_worker.py](../desktop_pet/assets/voice_worker.py)
- [desktop_pet/feature_preferences.py](../desktop_pet/feature_preferences.py)
- [desktop_pet/productivity_widgets.py](../desktop_pet/productivity_widgets.py)
- [desktop_pet/providers.py](../desktop_pet/providers.py)
- [desktop_pet/secrets.py](../desktop_pet/secrets.py)
- [desktop_pet/services/__init__.py](../desktop_pet/services/__init__.py)
- [desktop_pet/services/calendar.py](../desktop_pet/services/calendar.py)
- [desktop_pet/services/google.py](../desktop_pet/services/google.py)
- [desktop_pet/services/http.py](../desktop_pet/services/http.py)
- [desktop_pet/services/reminders.py](../desktop_pet/services/reminders.py)
- [desktop_pet/services/speech_recognition.py](../desktop_pet/services/speech_recognition.py)
- [desktop_pet/services/system_monitor.py](../desktop_pet/services/system_monitor.py)
- [desktop_pet/services/tasks.py](../desktop_pet/services/tasks.py)
- [desktop_pet/services/trivia.py](../desktop_pet/services/trivia.py)
- [desktop_pet/services/voice.py](../desktop_pet/services/voice.py)
- [desktop_pet/services/weather.py](../desktop_pet/services/weather.py)
- [desktop_pet/services/worker.py](../desktop_pet/services/worker.py)
- [desktop_pet/tools.py](../desktop_pet/tools.py)
- [desktop_pet/trivia_widgets.py](../desktop_pet/trivia_widgets.py)
- [docs/integrations.md](../docs/integrations.md)
- [docs/preferences-voice.png](../docs/preferences-voice.png)
- [docs/tools.png](../docs/tools.png)
- [docs/upgrade-report.md](../docs/upgrade-report.md)
- [requirements-integrations.txt](../requirements-integrations.txt)
- [requirements-voice.txt](../requirements-voice.txt)
- [scripts/check_packaged_workers.py](../scripts/check_packaged_workers.py)
- [tests/test_ai_providers.py](../tests/test_ai_providers.py)
- [tests/test_calendar.py](../tests/test_calendar.py)
- [tests/test_google.py](../tests/test_google.py)
- [tests/test_http_services.py](../tests/test_http_services.py)
- [tests/test_reminders.py](../tests/test_reminders.py)
- [tests/test_secrets.py](../tests/test_secrets.py)
- [tests/test_smart_integration.py](../tests/test_smart_integration.py)
- [tests/test_system_monitor.py](../tests/test_system_monitor.py)
- [tests/test_tasks.py](../tests/test_tasks.py)
- [tests/test_trivia.py](../tests/test_trivia.py)
- [tests/test_voice.py](../tests/test_voice.py)
- [tests/test_weather.py](../tests/test_weather.py)

## Files modified (19)

- [.github/workflows/windows.yml](../.github/workflows/windows.yml)
- [.gitignore](../.gitignore)
- [Biscuit.spec](../Biscuit.spec)
- [Build Windows App.bat](../Build%20Windows%20App.bat)
- [README.md](../README.md)
- [desktop_pet/ai.py](../desktop_pet/ai.py)
- [desktop_pet/app.py](../desktop_pet/app.py)
- [desktop_pet/panel.py](../desktop_pet/panel.py)
- [desktop_pet/preferences.py](../desktop_pet/preferences.py)
- [desktop_pet/storage.py](../desktop_pet/storage.py)
- [docs/compact.png](../docs/compact.png)
- [docs/companion.png](../docs/companion.png)
- [docs/preferences.png](../docs/preferences.png)
- [pyproject.toml](../pyproject.toml)
- [requirements-dev.txt](../requirements-dev.txt)
- [requirements.txt](../requirements.txt)
- [scripts/render_ui_preview.py](../scripts/render_ui_preview.py)
- [scripts/windows-version.txt](../scripts/windows-version.txt)
- [tests/test_storage.py](../tests/test_storage.py)
