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
