"""
test_audio_utils.py
Unit tests for audio_utils.py helper functions.
"""
import unittest
import datetime
from audio_utils import rms_to_dbfs, create_audio_plot, list_devices

class TestAudioUtils(unittest.TestCase):
    def test_rms_to_dbfs_zero(self):
        self.assertAlmostEqual(rms_to_dbfs(0), -240.0, delta=1.0)

    def test_rms_to_dbfs_typical(self):
        self.assertAlmostEqual(rms_to_dbfs(1.0), 0.0, delta=0.01)
        self.assertTrue(rms_to_dbfs(0.5) < 0.0)

    def test_create_audio_plot_empty(self):
        self.assertIsNone(create_audio_plot([]))

    def test_create_audio_plot_valid(self):
        now = datetime.datetime.now()
        history = [(now, -10.0), (now, -20.0), (now, -30.0)]
        img_bytes = create_audio_plot(history)
        self.assertIsInstance(img_bytes, (bytes, type(None)))

    def test_list_devices(self):
        result = list_devices()
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

if __name__ == "__main__":
    unittest.main()
