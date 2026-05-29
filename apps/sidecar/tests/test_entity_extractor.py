import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.core.entity_extractor import EntityExtractionChunk, extract_rule_entities


class EntityExtractorTest(unittest.TestCase):
    def test_rule_extractor_finds_supported_entity_types(self) -> None:
        candidates = extract_rule_entities(
            (
                EntityExtractionChunk(
                    chunk_id="chunk-1",
                    text=(
                        "Alpha Project budget for North Center at Hefei Site uses camera A1 "
                        "and switch S2. Amount is ¥1,200 on 2026-05-29. Ref DG-2026-001."
                    ),
                ),
            )
        )

        by_type = {candidate.entity_type: [] for candidate in candidates}
        for candidate in candidates:
            by_type.setdefault(candidate.entity_type, []).append(candidate)

        self.assertIn("Alpha Project", [item.entity_text for item in by_type["PROJECT"]])
        self.assertIn("North Center", [item.entity_text for item in by_type["ORG"]])
        self.assertIn("Hefei Site", [item.entity_text for item in by_type["LOCATION"]])
        self.assertTrue(any(item.normalized_text.startswith("¥1200") for item in by_type["MONEY"]))
        self.assertIn("2026-05-29", [item.normalized_text for item in by_type["DATE"]])
        self.assertIn("DG-2026-001", [item.normalized_text for item in by_type["ID_CODE"]])
        self.assertTrue(any(item.normalized_text.startswith("camera") for item in by_type["DEVICE"]))
        self.assertTrue(all(item.evidence_chunk_id == "chunk-1" for item in candidates))

    def test_rule_extractor_deduplicates_same_entity_per_chunk(self) -> None:
        candidates = extract_rule_entities(
            (
                EntityExtractionChunk(
                    chunk_id="chunk-1",
                    text="Alpha Project and Alpha Project are both mentioned.",
                ),
            )
        )

        project_candidates = [item for item in candidates if item.entity_type == "PROJECT"]
        self.assertEqual(len(project_candidates), 1)


if __name__ == "__main__":
    unittest.main()
