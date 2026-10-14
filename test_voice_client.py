import io
import unittest
import wave

import numpy as np

from voice_client import AudioConfig, record_utterance, rms, wav_bytes


def block(level: int, samples: int = 1_280) -> bytes:
    return np.full(samples, level, dtype=np.int16).tobytes()


class AudioTests(unittest.TestCase):
    def test_rms(self):
        self.assertAlmostEqual(rms(block(500)), 500.0, places=1)

    def test_wav_encoding(self):
        encoded = wav_bytes(block(100))
        with wave.open(io.BytesIO(encoded), "rb") as audio:
            self.assertEqual(audio.getframerate(), 16_000)
            self.assertEqual(audio.getnchannels(), 1)
            self.assertEqual(audio.getsampwidth(), 2)

    def test_record_stops_after_silence(self):
        cfg = AudioConfig(silence_seconds=0.16, min_seconds=0.08, max_seconds=2)
        source = iter([block(10), block(1_000), block(1_000), block(10), block(10), block(1_000)])
        result = record_utterance(source, noise_rms=10, cfg=cfg)
        self.assertGreater(len(result), 0)
        self.assertLess(len(result), 6 * 1_280 * 2)

    def test_record_times_out_when_there_is_no_speech(self):
        cfg = AudioConfig(max_seconds=0.16)
        result = record_utterance(iter([block(10), block(10)]), noise_rms=10, cfg=cfg)
        self.assertEqual(result, b"")


if __name__ == "__main__":
    unittest.main()
