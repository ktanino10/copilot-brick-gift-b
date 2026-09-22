"""Focused regression tests for recipient-neutral counter and spacing planning."""

from pathlib import Path
import sys
import unittest

from shapely.geometry import Polygon

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source/scripts"))
from legible_metrics import central_chords, closed_ring, plan_rows


class LegibilityTests(unittest.TestCase):
    def test_middle_band_does_not_report_a_curved_tip_as_zero(self):
        diamond = Polygon([(0, 2), (2, 4), (4, 2), (2, 0)])
        self.assertEqual(central_chords(diamond), (2.0, 2.0))

    def test_closed_sampling_endpoint_normalizes_only_roundoff(self):
        ring = [[0, 0], [1, 0], [1, 1], [0, 1e-14]]
        self.assertEqual(closed_ring(ring)[-1], ring[0])
        with self.assertRaisesRegex(ValueError, "closed wire"):
            closed_ring([[0, 0], [1, 0], [1, 1], [0, .01]])

    def test_planner_enlarges_inner_space_and_increases_gap_only(self):
        def glyph(index, x):
            return {"index": index, "character": "O", "faces": [{
                "outer": [[x, 0], [x + 4, 0], [x + 4, 6], [x, 6], [x, 0]],
                "holes": [[[x + 1.8, 1], [x + 2.2, 1], [x + 2.2, 5], [x + 1.8, 5], [x + 1.8, 1]]],
            }]}
        goals = {"counter_central_half_chord": 1.02, "e_exit_channel": 1.1,
                 "adjacent_glyph_clearance": 1.05}
        row = {"number": 1, "glyphs": [glyph(0, 0), glyph(1, 4.2)]}
        planned = plan_rows([row], goals, 10)[0]
        self.assertAlmostEqual(planned["glyphs"][0]["counters"][0]["scale_xy"][0], 2.55)
        self.assertAlmostEqual(planned["glyphs"][1]["extra_x_mm"], .85, places=6)
        with self.assertRaisesRegex(ValueError, "do not shrink or truncate"):
            plan_rows([row], goals, 8)


if __name__ == "__main__":
    unittest.main()
