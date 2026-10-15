#!/usr/bin/env python3
"""Wake-word driven terminal client for voice_ai_server."""

from __future__ import annotations

import argparse
import glob
import io
import json
import os
import signal
import sys
import time
import uuid
import wave
from collections import deque
from dataclasses import dataclass
from typing import Iterator

import numpy as np
import requests


SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2
CHANNELS = 1
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


@dataclass(frozen=True)
class AudioConfig:
    block_samples: int = 1_280  # 80 ms; native openWakeWord frame size.
    silence_seconds: float = 2.5
    max_seconds: float = 20.0
    min_seconds: float = 0.5
    pre_roll_seconds: float = 0.24
    silence_multiplier: float = 2.0
    min_silence_rms: float = 100.0


@dataclass(frozen=True)
class AudioResponse:
    data: bytes
    content_type: str


def rms(pcm: bytes) -> float:
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0


def wav_bytes(pcm: bytes) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)
    return output.getvalue()


class WakeWordDetector:
    def __init__(self, model: str, threshold: float):
        try:
            from openwakeword.model import Model
        except ImportError as exc:
            raise RuntimeError(
                "openWakeWord is missing. Run: pip install -r requirements.txt"
            ) from exc
        model_path = model
        if not os.path.isfile(model_path):
            candidates = sorted(glob.glob(os.path.join(MODEL_DIR, f"{model}_v*.onnx")))
            exact_path = os.path.join(MODEL_DIR, f"{model}.onnx")
            if os.path.isfile(exact_path):
                model_path = exact_path
            elif candidates:
                model_path = candidates[-1]

        self.model_name = os.path.splitext(os.path.basename(model_path))[0]
        self.threshold = threshold
        try:
            self._model = Model(
                wakeword_models=[model_path],
                inference_framework="onnx",
                melspec_model_path=os.path.join(MODEL_DIR, "melspectrogram.onnx"),
                embedding_model_path=os.path.join(MODEL_DIR, "embedding_model.onnx"),
            )
        except Exception as exc:
            raise RuntimeError(
                f"Could not load wake-word model '{model}' from '{MODEL_DIR}'. "
                "See the README for model download instructions."
            ) from exc

    def detected(self, pcm: bytes) -> tuple[bool, float]:
        prediction = self._model.predict(np.frombuffer(pcm, dtype=np.int16))
        score = float(prediction.get(self.model_name, max(prediction.values(), default=0.0)))
        return score >= self.threshold, score

    def reset(self) -> None:
        self._model.reset()


class Microphone:
    def __init__(self, device: str | int | None, block_samples: int):
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError(
                "sounddevice is missing. Run: pip install -r requirements.txt"
            ) from exc
        self._sd = sd
        self._device = device
        self._block_samples = block_samples
        self._stream = None

    def __enter__(self) -> "Microphone":
        self._stream = self._sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=self._block_samples,
            device=self._device,
            channels=CHANNELS,
            dtype="int16",
        )
        self._stream.start()
        return self

    def __exit__(self, *_args: object) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()

    def blocks(self) -> Iterator[bytes]:
        if self._stream is None:
            raise RuntimeError("The microphone is not open")
        while True:
            data, overflowed = self._stream.read(self._block_samples)
            if overflowed:
                print("\n[Warning] Microphone input overflow.", file=sys.stderr)
            yield bytes(data)


def record_utterance(blocks: Iterator[bytes], noise_rms: float, cfg: AudioConfig) -> bytes:
    """Record until speech has started and then remained quiet long enough."""
    frame_seconds = cfg.block_samples / SAMPLE_RATE
    silence_limit = max(1, round(cfg.silence_seconds / frame_seconds))
    max_blocks = max(1, round(cfg.max_seconds / frame_seconds))
    min_blocks = max(1, round(cfg.min_seconds / frame_seconds))
    pre_roll = deque(maxlen=max(1, round(cfg.pre_roll_seconds / frame_seconds)))
    threshold = max(cfg.min_silence_rms, noise_rms * cfg.silence_multiplier)
    captured: list[bytes] = []
    speech_started = False
    quiet_blocks = 0

    for total_blocks, block in enumerate(blocks, start=1):
        level = rms(block)
        if not speech_started:
            pre_roll.append(block)
            if level >= threshold:
                speech_started = True
                captured.extend(pre_roll)
                quiet_blocks = 0
                print("Recording...", flush=True)
            elif total_blocks >= max_blocks:
                break
            continue

        captured.append(block)
        quiet_blocks = quiet_blocks + 1 if level < threshold else 0
        if len(captured) >= max_blocks:
            break
        if len(captured) >= min_blocks and quiet_blocks >= silence_limit:
            break
    return b"".join(captured)


def send_voice(
    server_url: str,
    audio: bytes,
    session_id: str,
    language: str | None,
    api_key: str | None,
    timeout: float,
    response_format: str = "text",
) -> dict | AudioResponse:
    url = server_url.rstrip("/") + "/v1/voice/chat"
    api_response_format = "json" if response_format == "text" else "audio"
    form = {"session_id": session_id, "response_format": api_response_format}
    if language:
        form["language"] = language
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    response = requests.post(
        url,
        data=form,
        files={"audio": ("recording.wav", wav_bytes(audio), "audio/wav")},
        headers=headers,
        timeout=timeout,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        try:
            detail = response.json().get("detail") or response.text
        except ValueError:
            detail = response.text
        raise RuntimeError(f"Server returned HTTP {response.status_code}: {detail}") from exc
    if response_format == "audio":
        if not response.content:
            raise RuntimeError("Server returned an empty audio response")
        return AudioResponse(
            data=response.content,
            content_type=response.headers.get("Content-Type", "application/octet-stream")
            .split(";", 1)[0]
            .strip()
            .lower(),
        )

    payload = response.json()
    if "text" not in payload:
        raise RuntimeError("Server response is missing the 'text' field")
    return payload


def play_audio(response: AudioResponse) -> None:
    """Play an uncompressed WAV response through the default output device."""
    try:
        with wave.open(io.BytesIO(response.data), "rb") as wav:
            if wav.getcomptype() != "NONE":
                raise RuntimeError(f"Unsupported WAV compression: {wav.getcomptype()}")
            sample_widths = {1: "uint8", 2: "int16", 3: "int24", 4: "int32"}
            dtype = sample_widths.get(wav.getsampwidth())
            if dtype is None:
                raise RuntimeError(f"Unsupported WAV sample width: {wav.getsampwidth()} bytes")
            channels = wav.getnchannels()
            sample_rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())
    except (wave.Error, EOFError) as exc:
        raise RuntimeError(
            f"Server returned {response.content_type}, but the client requires PCM WAV audio"
        ) from exc

    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError("sounddevice is missing. Run: pip install -r requirements.txt") from exc

    with sd.RawOutputStream(
        samplerate=sample_rate,
        channels=channels,
        dtype=dtype,
    ) as stream:
        stream.write(frames)


def choose_response_format(default: str = "text") -> str:
    """Ask an interactive user whether the AI should answer with text or audio."""
    choices = {"1": "text", "text": "text", "2": "audio", "audio": "audio"}
    while True:
        try:
            answer = input(
                f"Output type: [1] text, [2] audio (default: {default}): "
            ).strip().lower()
        except EOFError:
            return default
        if not answer:
            return default
        if answer in choices:
            return choices[answer]
        print("Please enter 1/text or 2/audio.", file=sys.stderr)


def calibrate(blocks: Iterator[bytes], seconds: float, block_samples: int) -> float:
    count = max(1, round(seconds * SAMPLE_RATE / block_samples))
    print(f"Calibrating ambient noise for {seconds:g} seconds - please stay quiet...", flush=True)
    levels = [rms(next(blocks)) for _ in range(count)]
    return float(np.percentile(levels, 75))


def load_config(path: str = CONFIG_PATH) -> dict:
    try:
        with open(path, encoding="utf-8") as config_file:
            config = json.load(config_file)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read configuration file '{path}': {exc}") from exc
    if not isinstance(config, dict):
        raise RuntimeError(f"Configuration file '{path}' must contain a JSON object")
    return config


def config_value(config: dict, key: str, env_name: str, fallback: object = None) -> object:
    return os.getenv(env_name, config.get(key, fallback))


def parse_args(config: dict | None = None) -> argparse.Namespace:
    config = load_config() if config is None else config
    parser = argparse.ArgumentParser(description="Wake-word voice assistant for the terminal")
    parser.add_argument("--server", default=config_value(config, "server", "VOICE_SERVER_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--api-key", default=config_value(config, "api_key", "VOICE_API_KEY"))
    parser.add_argument("--language", default=config_value(config, "language", "VOICE_LANGUAGE", "en"))
    parser.add_argument("--session-id", default=config_value(config, "session_id", "VOICE_SESSION_ID") or f"terminal-{uuid.uuid4()}")
    parser.add_argument("--wake-word", default=config_value(config, "wake_word", "WAKE_WORD", "hey_jarvis"))
    parser.add_argument("--threshold", type=float, default=float(config_value(config, "threshold", "WAKE_THRESHOLD", 0.5)))
    parser.add_argument("--device", default=config_value(config, "device", "MIC_DEVICE"), help="Input device name or index")
    parser.add_argument("--timeout", type=float, default=float(config.get("timeout", 180.0)), help="HTTP timeout in seconds")
    parser.add_argument(
        "--response-format",
        choices=("text", "audio"),
        help="AI output type; if omitted, ask when the program starts",
    )
    parser.add_argument(
        "--silence-seconds",
        type=float,
        default=float(config_value(config, "silence_seconds", "VOICE_SILENCE_SECONDS", 2.5)),
        help="Continuous silence required to finish an utterance",
    )
    parser.add_argument(
        "--silence-multiplier",
        type=float,
        default=float(config_value(config, "silence_multiplier", "VOICE_SILENCE_MULTIPLIER", 2.0)),
        help="Ambient noise multiplier used as the speech threshold",
    )
    parser.add_argument(
        "--min-silence-rms",
        type=float,
        default=float(config_value(config, "min_silence_rms", "VOICE_MIN_SILENCE_RMS", 100.0)),
        help="Minimum RMS speech threshold",
    )
    parser.add_argument("--list-devices", action="store_true", help="List audio devices and exit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.list_devices:
        try:
            import sounddevice as sd
        except ImportError:
            print("sounddevice is missing. Run: pip install -r requirements.txt", file=sys.stderr)
            return 2
        print(sd.query_devices())
        return 0

    configured_format = str(load_config().get("response_format", "text")).lower()
    if configured_format not in {"text", "audio"}:
        configured_format = "text"
    response_format = args.response_format or choose_response_format(configured_format)

    device: str | int | None = args.device
    if isinstance(device, str) and device.isdigit():
        device = int(device)
    cfg = AudioConfig(
        silence_seconds=args.silence_seconds,
        silence_multiplier=args.silence_multiplier,
        min_silence_rms=args.min_silence_rms,
    )
    running = True

    def stop(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    try:
        detector = WakeWordDetector(args.wake_word, args.threshold)
        with Microphone(device, cfg.block_samples) as microphone:
            blocks = microphone.blocks()
            noise = calibrate(blocks, 1.5, cfg.block_samples)
            print(
                f"Ready. Say '{args.wake_word}' (Ctrl+C to exit).\n"
                f"Session: {args.session_id}\n"
                f"Output: {response_format}",
                flush=True,
            )
            while running:
                block = next(blocks)
                found, _score = detector.detected(block)
                if not found:
                    continue
                print(f"\nWake word '{args.wake_word}' detected. Ask your question.", flush=True)
                detector.reset()
                audio = record_utterance(blocks, noise, cfg)
                if not audio:
                    print("No question detected; returning to wake-word mode.", flush=True)
                    continue
                print("Sending audio to the AI server...", flush=True)
                try:
                    result = send_voice(
                        args.server, audio, args.session_id, args.language or None,
                        args.api_key, args.timeout, response_format,
                    )
                    if isinstance(result, AudioResponse):
                        print("AI: playing audio response...", flush=True)
                        play_audio(result)
                        print()
                    else:
                        print(f"You: {result.get('transcript', '(no transcript)')}")
                        print(f"AI: {result['text']}\n")
                except (requests.RequestException, RuntimeError, ValueError) as exc:
                    print(f"Error: {exc}\n", file=sys.stderr)
                print(f"Waiting for '{args.wake_word}'...", flush=True)
    except (RuntimeError, OSError) as exc:
        print(f"Startup error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        pass
    print("Stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
