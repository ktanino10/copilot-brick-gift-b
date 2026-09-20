#!/usr/bin/env python3
"""Reject plausible but misleading B print/assembly associations."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from verify_guide_mapping import verify_mapping


MAPPING = json.loads((Path(__file__).resolve().parents[1] / "guide/index.mapping.json").read_text())


class GuideMappingTests(unittest.TestCase):
    def test_actual_mapping(self):
        self.assertEqual(verify_mapping(MAPPING)["slots"], 150)

    def test_wrong_print_position(self):
        modified = deepcopy(MAPPING)
        modified["plates"][1]["slots"][2]["print_position"][0] += 1
        with self.assertRaisesRegex(ValueError, "print transform"):
            verify_mapping(modified)

    def test_swapped_first_part(self):
        modified = deepcopy(MAPPING)
        modified["plates"][1]["slots"][2]["suggested_placement"] = "B-002"
        with self.assertRaisesRegex(ValueError, "assignment"):
            verify_mapping(modified)

    def test_missing_interchangeable_candidate(self):
        modified = deepcopy(MAPPING)
        modified["plates"][0]["slots"][0]["candidate_placements"] = ["B-006"]
        with self.assertRaisesRegex(ValueError, "interchangeable"):
            verify_mapping(modified)

    def test_wrong_front_rotation(self):
        modified = deepcopy(MAPPING)
        modified["placements"][19]["rotation"] = [0, 0, 0]
        with self.assertRaisesRegex(ValueError, "transform"):
            verify_mapping(modified)

    def test_wrong_step_boundary(self):
        modified = deepcopy(MAPPING)
        modified["steps"][1]["first_index"] = 0
        with self.assertRaisesRegex(ValueError, "boundaries"):
            verify_mapping(modified)

    def test_stale_inputs(self):
        modified = deepcopy(MAPPING)
        modified["inputs_sha256"]["assembly"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            verify_mapping(modified)


if __name__ == "__main__":
    unittest.main()
