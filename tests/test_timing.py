"""What voice.log says about timing has to be what happened."""
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
from tts import KokoroEngine  # noqa: E402


class FirstSound(unittest.TestCase):
    def test_a_long_first_sentence_does_not_count_as_a_long_wait(self):
        # The player takes a sentence at the speed it plays it, so writing eight seconds of sound
        # to it takes seconds. That is playing, not waiting: the log said 3 to 8 s for lines
        # whose sound had started within one.
        tmp = tempfile.mkdtemp(prefix="cs-test-")
        with open(os.path.join(tmp, "paplay"), "w") as f:
            f.write("#!/bin/sh\nsleep 0.6\ncat > /dev/null\n")  # a player that is slow to take what it is given
        os.chmod(os.path.join(tmp, "paplay"), 0o755)
        engine = KokoroEngine("", 1.0, "any")
        engine.voices = {"any"}
        engine._pcm = lambda text, voice: b"\0" * 400_000  # more than a pipe holds
        with mock.patch.dict(os.environ, {"PATH": tmp + os.pathsep + os.environ["PATH"]}):
            first = engine.speak(["A long first sentence."], "any")
        self.assertIsNotNone(first)
        self.assertLess(first, 0.3)


if __name__ == "__main__":
    unittest.main()


class WhereTheVoiceIsMade(unittest.TestCase):
    """Kokoro on the graphics card when it can be, else on the processor (`voice_device`)."""

    def session(self, device, providers=("CUDAExecutionProvider", "CPUExecutionProvider"), libraries="", fails=False):
        import onnxruntime
        made = []

        class Session:
            def __init__(self, path, sess_options=None, providers=()):
                if fails and providers[0] == "CUDAExecutionProvider":
                    raise RuntimeError("CUDA failure 2: out of memory")
                made.append(list(providers))
                self.providers = list(providers)

            def get_providers(self):
                return self.providers

        engine = KokoroEngine("", 1.0, "af_heart", device=device)
        with mock.patch.object(onnxruntime, "InferenceSession", Session), \
                mock.patch.object(onnxruntime, "get_available_providers", lambda: list(providers)), \
                mock.patch("gpu.load", lambda parts=None, roots=None: libraries):
            engine._session("model.onnx")
        return engine, made

    def test_the_card_when_it_can(self):
        for device in ("auto", "gpu"):
            engine, made = self.session(device)
            self.assertEqual(made, [["CUDAExecutionProvider", "CPUExecutionProvider"]])
            self.assertEqual((engine.running, engine.why_not_gpu), ("the graphics card", ""))

    def test_else_the_processor_and_why(self):
        engine, made = self.session("auto", providers=("CPUExecutionProvider",))
        self.assertEqual((made, engine.running), ([["CPUExecutionProvider"]], "the processor"))
        self.assertEqual(engine.why_not_gpu, "onnxruntime-gpu is not installed")
        engine, made = self.session("gpu", libraries="NVIDIA's cufft not installed")
        self.assertEqual((made, engine.why_not_gpu), ([["CPUExecutionProvider"]], "NVIDIA's cufft not installed"))
        engine, made = self.session("gpu", fails=True)
        self.assertEqual(made, [["CPUExecutionProvider"]])
        self.assertIn("out of memory", engine.why_not_gpu)
        engine, made = self.session("cpu")
        self.assertEqual((made, engine.why_not_gpu), ([["CPUExecutionProvider"]], ""))  # the card never asked

    def test_the_libraries_each_part_needs(self):
        import gpu
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "cublas", "lib"))
            open(os.path.join(root, "cublas", "lib", "libcublas.so.12"), "w").close()
            self.assertEqual(gpu.load(gpu.WHISPER_PARTS, [root]), "NVIDIA's cudnn not installed")
            self.assertIn("cuda_runtime", gpu.load(gpu.VOICE_PARTS, [root]))
