# Smart companion integrations

Biscuit keeps the native desktop pet, chat, five activities, reactions, and Windows launcher. Every integration is optional. The default offline replies and animations need no account or network.

## AI providers

Open the existing gear → AI provider. Choose Offline, Ollama, Groq, or Custom. Companion preferences and AI connection saves remain separate.

- **Ollama:** install Ollama yourself, install a model you have chosen, and run its server. Select Ollama, keep `http://localhost:11434/v1` or enter your trusted local endpoint, click **Test / models**, and choose an installed ID. Biscuit checks PATH for the executable and tests the server independently; it never pulls a model. Model hardware requirements and licenses vary.
- **Groq:** create your own key, select Groq, discover models from `/models`, and select a currently supported ID. Availability and rate limits depend on your account. No model ID is assumed permanent. Groq's free offering is limited; paid usage may incur charges.
- **Custom:** existing OpenAI-compatible URL/model settings and the original `api-key` credential entry continue to work. Groq and Ollama use separate credential entries.

Save the AI connection to apply it. Existing messages stay visible. A changed endpoint starts new context by default; check **Include earlier chat** only if you want that context sent to the new destination. Clearing chat is the only action that erases completed conversation history. History is in memory, not on disk.

Failure messages never include provider bodies or keys. An explicit **Use offline reply** action provides local fallback. You may enable automatic *offline* fallback; the app never retries chat with another hosted provider automatically. To use another configured provider, select it in Preferences. Optional per-day cloud-message and response-token limits help control use; an app limit of zero means no app-imposed limit, not free or unlimited provider access. Rate-limit cooldowns apply; chat POSTs are never automatically retried.

## Source verification and costs

Source review started on **2026-10-20**. The workspace proxy blocks several vendor documentation hosts (HTTP CONNECT 403); their current numeric pricing/quotas could not be verified here. Check the linked official pages before enabling services. This is not a claim of unlimited or permanently free access.

| Component | Official source and observed constraint |
| --- | --- |
| Ollama | [OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility); local inference has no hosted subscription, but selected model licenses/hardware requirements apply. This documentation host was blocked here. |
| Groq | [Rate limits](https://console.groq.com/docs/rate-limits), [models](https://console.groq.com/docs/models), [official client](https://github.com/groq/groq-python); client README was accessible, live pricing/quota pages were blocked. |
| Open-Meteo | [Official README](https://github.com/open-meteo/open-meteo), [terms](https://open-meteo.com/en/terms); accessible official README describes free **non-commercial** access and CC BY 4.0 data attribution. Commercial usage needs separate terms. Live terms host was blocked. |
| Piper | [Current project](https://github.com/OHF-Voice/piper1-gpl), [CLI](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/CLI.md); current project is GPL-3.0. Voices have separate model licenses. Keep external Piper installation/voices separate from Biscuit unless you have reviewed distribution obligations. |
| Faster Whisper | [Project and MIT license](https://github.com/SYSTRAN/faster-whisper); README and license were accessible. Model licenses and download size vary. |
| Google Tasks / Calendar | [Tasks usage](https://developers.google.com/workspace/tasks/v1/usage), [Calendar quotas](https://developers.google.com/workspace/calendar/api/guides/quota), [desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app); vendor hosts blocked here. Google account/project, enabled APIs, OAuth client, quotas, and possibly app verification apply. |
| Open Trivia DB | [API configuration and terms](https://opentdb.com/api_config.php); host blocked here. Observe its request limits and attribution; no unlimited-access claim. |
| psutil | [BSD 3-Clause license](https://github.com/giampaolo/psutil/blob/master/LICENSE); license was accessible. Monitoring stays on the computer. |

Tests use local mock HTTP servers and fixtures. They do not consume paid API quota, access a Google account, or download AI/voice models.

## Weather and system awareness

Use **Tools → Weather** to search for a city and explicitly select it. This enables weather for that location; no GPS/IP geolocation is requested. Open-Meteo receives the selected coordinates/city search. The page shows current °C conditions, a three-day forecast, chance of rain, attribution, and whether results are cached/stale. Refresh intervals are configurable (15–180 minutes; default 30). Manual refresh is throttled to once a minute, city searches to once every three seconds, and safe reads have at most one delayed retry. A local weather cache provides clearly labeled last-known conditions when offline. Disable weather in the gear's Weather group to stop background requests.

Optional weather reactions use existing Biscuit animations and do not interrupt Work, dragging, greeting, or another reaction. They are off by default. Open-Meteo's public free service is for **non-commercial use**; review its commercial terms before distributing a commercial service. Weather data attribution is Open-Meteo / CC BY 4.0.

Enable read-only monitoring in the gear's System group, then open **Tools → System status**. Install the optional extra with `python -m pip install ".[system]"` for psutil CPU/RAM/battery values. It samples every 30 seconds without examining processes or application contents. On Windows, a supported power-status API can supply battery information when psutil is unavailable. Desktop PCs without batteries are handled normally. Optional low-battery/charging notices are edge-triggered and throttled; focus sessions suppress them. Nothing is uploaded. These Windows power/tray behaviors still require native Windows verification.

## Local voice: Piper and Faster Whisper

Voice is **off by default**. It never starts a microphone automatically. Text, local reminders, animations, and chat continue working with no speech packages installed.

Create a separate Python 3.12 environment and install `requirements-voice.txt`. In the gear's Voice group, select that environment's Python executable (`voice-env\Scripts\python.exe` on Windows). A packaged Biscuit executable also uses this external environment; heavy speech libraries/models are intentionally not built into the small default bundle. Piper is GPL-3.0 and each voice has its own model license. Review them before distributing speech environments or voices; the app does not bundle Piper.

Choose one of:

- **Text only:** no speech inference or playback; Mic explains how to enable voice.
- **Text + spoken replies:** AI/offline responses are synthesized locally with Piper and played through Qt.
- **Push-to-talk + spoken replies:** click Mic to begin, then Stop to transcribe. Recording stops after 60 seconds or the memory limit. Review/edit the recognized text and explicitly press Send. Auto-detect, English, and Filipino/Tagalog are supported by multilingual Whisper models; accuracy depends on the model, accent, noise, and hardware.

Choose a local Piper `.onnx` file with its adjacent `.onnx.json`, and a local Faster Whisper model directory containing `model.bin`. You can import existing models without downloading anything. **Download Piper voice…** offers `en_US-lessac-medium`; **Download Whisper tiny…** offers the multilingual tiny model. Each asks for a destination and explicit confirmation before contacting Hugging Face. Model sizes are approximate (Piper roughly 60 MB, Whisper tiny roughly 75 MB) and may change. Tiny prioritizes CPU size/speed; install a larger multilingual model manually if you need better Tagalog recognition. Downloaded files are reused; normal transcription passes `local_files_only=True` and never downloads a model.

Change speech speed, volume, voice, input device, and language in the Voice group. **Sound** mutes/unmutes replies; **Tools → Voice** provides sample speech and a stop/cancel action for playback, recording, inference, and downloads. Generating speech/transcribing/downloading runs in cancellable worker processes and does not freeze the Qt event loop. While speaking, a resting Biscuit can wag its tail without disturbing Work.

Microphone PCM stays in memory and is passed to the local worker through pipes. Recordings are not written to disk. Synthesized reply audio uses a temporary WAV removed on shutdown. Recognized text is not sent to AI until you press Send. Device/permission/model errors are shown without exposing transcripts in logs. Actual microphone capture, speakers, Piper voices, and Whisper inference still need validation with your installed models and Windows audio devices; automated tests exercise the pipeline and local-processing constraints with mocked backends.
