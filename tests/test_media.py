import array
import tempfile
import unittest
import wave
from pathlib import Path

from PIL import Image, ImageDraw

from videopipe.backends.cpu import CPUGenerator
from videopipe.media import inspect_video, normalize_clip, run_ffmpeg
from videopipe.models import MediaConfig, Shot


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        image = Image.new("RGB", (240, 160), "#dbb28d")
        ImageDraw.Draw(image).ellipse((50, 20, 170, 140), fill="#dc531c")
        self.reference = self.directory / "cup.png"
        image.save(self.reference)
        self.shot = Shot(id="cup", prompt="An orange cup", reference_images=[self.reference],
                         duration=1, width=160, height=96, fps=12)
        self.clip = CPUGenerator().generate(self.shot, self.directory, attempt=1)
        self.config = MediaConfig(width=192, height=128, fps=12)

    def test_normalize_preserves_native_audio_tail_when_duration_omitted(self):
        source = self.directory / "native-audio.mp4"
        run_ffmpeg([
            "-loglevel", "error", "-i", str(self.clip), "-f", "lavfi", "-i",
            "sine=frequency=440:sample_rate=48000:duration=1.5",
            "-c:v", "copy", "-c:a", "aac", str(source),
        ])
        measured = inspect_video(source)
        # The original planned shot is one second; its native output audio extends beyond that.
        normalized = normalize_clip(source, self.directory / "retained.mp4", config=self.config)
        info = inspect_video(normalized)
        self.assertAlmostEqual(info.duration, measured.duration, delta=0.09)
        self.assertGreater(info.duration, self.shot.duration + 0.4)
        self.assertTrue(info.has_audio)
        audio = self.directory / "retained.wav"
        run_ffmpeg(["-loglevel", "error", "-i", str(normalized), "-vn", "-ac", "1",
                    "-c:a", "pcm_s16le", str(audio)])
        with wave.open(str(audio)) as stream:
            samples = array.array("h", stream.readframes(stream.getnframes()))
            rate = stream.getframerate()
        self.assertGreater(max(abs(sample) for sample in samples[int(rate * 1.2):int(rate * 1.4)]), 500)


if __name__ == "__main__":
    unittest.main()
