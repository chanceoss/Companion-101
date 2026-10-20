"""Isolated optional speech worker. JSON pipes only; never record or log audio."""

import base64
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")


def run(operation, data):
    if operation == "protocol_test":
        return {"ready": True}
    if operation == "speak":
        import wave
        from piper import PiperVoice, SynthesisConfig

        model = Path(data["model"])
        if not model.is_file() or not Path(str(model) + ".json").is_file():
            raise ValueError("voice_model")
        voice = PiperVoice.load(str(model))
        config = SynthesisConfig(
            length_scale=1 / max(0.5, min(2, float(data.get("speed", 1))))
        )
        with wave.open(data["output"], "wb") as wav:
            voice.synthesize_wav(data["text"][:4000], wav, syn_config=config)
        return {"path": data["output"]}
    if operation == "transcribe":
        import numpy as np
        from faster_whisper import WhisperModel

        model_path = Path(data["model"])
        if not model_path.is_dir() or not (model_path / "model.bin").is_file():
            raise ValueError("whisper_model")
        raw = base64.b64decode(data["audio"], validate=True)
        dtype = {"Int16": "<i2", "Int32": "<i4", "UInt8": "u1", "Float": "<f4"}[
            data["format"]
        ]
        samples = np.frombuffer(raw, dtype=dtype).astype(np.float32)
        if data["format"] == "UInt8":
            samples = (samples - 128) / 128
        elif data["format"] == "Int16":
            samples /= 32768
        elif data["format"] == "Int32":
            samples /= 2147483648
        channels = int(data["channels"])
        rate = int(data["rate"])
        samples = (
            samples[: len(samples) // channels * channels]
            .reshape(-1, channels)
            .mean(axis=1)
        )
        if rate != 16000 and len(samples):
            samples = np.interp(
                np.arange(round(len(samples) * 16000 / rate)) * rate / 16000,
                np.arange(len(samples)),
                samples,
            ).astype(np.float32)
        model = WhisperModel(
            str(model_path), device="cpu", compute_type="int8", local_files_only=True
        )
        language = data.get("language") or None
        segments, _ = model.transcribe(
            samples, language=language, beam_size=3, vad_filter=True
        )
        return {
            "text": " ".join(segment.text.strip() for segment in segments).strip()[
                :4000
            ]
        }
    if operation == "download_whisper":
        from huggingface_hub import snapshot_download

        size = data["size"]
        if size not in ("tiny", "base", "small"):
            raise ValueError("model_size")
        path = snapshot_download(
            repo_id="Systran/faster-whisper-" + size,
            local_dir=data["directory"],
            allow_patterns=[
                "config.json",
                "model.bin",
                "tokenizer.json",
                "vocabulary.*",
                "preprocessor_config.json",
            ],
            max_workers=2,
            token=False,
        )
        return {"model": path}
    if operation == "download_piper":
        from huggingface_hub import hf_hub_download

        prefix = "en/en_US/lessac/medium/"
        paths = []
        for filename in (
            "en_US-lessac-medium.onnx",
            "en_US-lessac-medium.onnx.json",
            "MODEL_CARD",
        ):
            paths.append(
                hf_hub_download(
                    repo_id="rhasspy/piper-voices",
                    filename=prefix + filename,
                    local_dir=data["directory"],
                    token=False,
                )
            )
        return {"model": paths[0]}
    raise ValueError("operation")


def main():
    operation = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        data = json.loads(sys.stdin.buffer.read(40 * 1024 * 1024))
        # Libraries may print progress; never mix it into the result protocol.
        with redirect_stdout(sys.stderr):
            result = run(operation, data)
        print(json.dumps({"ok": True, "result": result}))
    except ImportError:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "Optional speech packages are missing in the selected Python environment. See the voice setup guide.",
                }
            )
        )
    except Exception:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "Local speech processing failed. Check the selected model, device, free memory, and speech environment. No recording was saved.",
                }
            )
        )


if __name__ == "__main__":
    main()
