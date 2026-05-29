import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar.core.profile_builder import (
    ProfileChunkInput,
    ProfileFileInput,
    build_rule_profile,
)


class ProfileBuilderTest(unittest.TestCase):
    def test_builder_prioritizes_sheet_title_and_structural_evidence(self) -> None:
        draft = build_rule_profile(
            ProfileFileInput(
                file_id="file-budget",
                filename="alpha_budget_2026.xlsx",
                extension=".xlsx",
                source_type="office",
            ),
            (
                _chunk(
                    "chunk-late-note",
                    4,
                    "paragraph",
                    "Implementation note",
                    "Appendix",
                    "A late appendix paragraph mentions alpha budget archive details.",
                ),
                _chunk(
                    "chunk-sheet-budget",
                    0,
                    "sheet",
                    "Budget",
                    "Budget",
                    "Sheet: Budget Headers: Department, Owner, Amount Key columns: Owner",
                    sheet_name="Budget",
                    token_count=12,
                ),
                _chunk(
                    "chunk-summary",
                    1,
                    "paragraph",
                    "Summary",
                    "Budget > Summary",
                    "North Center owns the 2026 alpha project budget.",
                ),
            ),
        )

        self.assertEqual(draft.document_role, "spreadsheet")
        self.assertGreaterEqual(draft.role_confidence, 0.8)
        self.assertEqual(draft.central_idea, "Alpha Budget 2026 - Budget")
        self.assertEqual(draft.evidence_chunks[0].chunk_id, "chunk-sheet-budget")
        self.assertIn("sheet", draft.evidence_chunks[0].source)
        self.assertIn("Budget", draft.keywords)
        self.assertGreaterEqual(draft.profile_confidence, 0.8)

    def test_builder_uses_slide_title_for_presentations(self) -> None:
        draft = build_rule_profile(
            ProfileFileInput(
                file_id="file-review",
                filename="quarterly_review.pptx",
                extension=".pptx",
                source_type="office",
            ),
            (
                _chunk(
                    "chunk-slide-1",
                    0,
                    "slide",
                    "Quarterly Review",
                    "Quarterly Review",
                    "Slide 1 Title: Quarterly Review Body: Revenue and risk overview.",
                    slide_no=1,
                    token_count=10,
                ),
                _chunk(
                    "chunk-slide-2",
                    1,
                    "slide",
                    "Risks",
                    "Risks",
                    "Slide 2 Title: Risks Body: Customer renewal pressure.",
                    slide_no=2,
                    token_count=9,
                ),
            ),
        )

        self.assertEqual(draft.document_role, "presentation_deck")
        self.assertEqual(draft.central_idea, "Quarterly Review")
        self.assertEqual(draft.evidence_chunks[0].chunk_id, "chunk-slide-1")
        self.assertIn("slide", draft.evidence_chunks[0].source)
        self.assertIn("Quarterly", draft.keywords)


def _chunk(
    chunk_id: str,
    chunk_index: int,
    chunk_type: str,
    heading: str,
    section_path: str,
    text: str,
    *,
    sheet_name: str | None = None,
    slide_no: int | None = None,
    token_count: int | None = 8,
) -> ProfileChunkInput:
    return ProfileChunkInput(
        chunk_id=chunk_id,
        chunk_index=chunk_index,
        chunk_type=chunk_type,
        page_no=None,
        sheet_name=sheet_name,
        slide_no=slide_no,
        heading=heading,
        section_path=section_path,
        text=text,
        token_count=token_count,
    )


if __name__ == "__main__":
    unittest.main()
