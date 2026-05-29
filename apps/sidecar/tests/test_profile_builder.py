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
    def test_builder_generates_excel_strategy_for_engineering_checklist(self) -> None:
        draft = build_rule_profile(
            ProfileFileInput(
                file_id="file-checklist",
                filename="engineering_material_checklist.xlsx",
                extension=".xlsx",
                source_type="office",
            ),
            (
                _chunk(
                    "chunk-sheet-materials",
                    0,
                    "sheet",
                    "Materials",
                    "Materials",
                    "\n".join(
                        [
                            "Sheet: Materials",
                            "Headers: Item, Quantity, Unit Cost, Owner, Status",
                            "Key columns: Item, Quantity, Owner, Status",
                            "Amount columns: Unit Cost",
                            "Preview rows:",
                            "Pump A | 2 | ¥1200 | North Center | Ordered",
                            "Valve B | 6 | ¥80 | Warehouse | Pending",
                        ]
                    ),
                    sheet_name="Materials",
                    token_count=28,
                ),
                _chunk(
                    "chunk-summary",
                    1,
                    "sheet",
                    "Summary",
                    "Summary",
                    "\n".join(
                        [
                            "Sheet: Summary",
                            "Headers: Project, Budget, Owner",
                            "Amount columns: Budget",
                            "Preview rows:",
                            "Alpha Plant | ¥50000 | North Center",
                        ]
                    ),
                    sheet_name="Summary",
                    token_count=18,
                ),
            ),
        )

        self.assertEqual(draft.document_role, "spreadsheet")
        self.assertGreaterEqual(draft.role_confidence, 0.8)
        self.assertEqual(
            draft.central_idea,
            "Engineering Material Checklist - Materials, Summary engineering inventory",
        )
        self.assertEqual(draft.evidence_chunks[0].chunk_id, "chunk-sheet-materials")
        self.assertIn("sheet", draft.evidence_chunks[0].source)
        excel_profile = draft.strategy_data["excel_profile"]
        self.assertEqual(excel_profile["sheet_count"], 2)
        self.assertEqual(excel_profile["main_sheets"][0], "Materials")
        self.assertEqual(excel_profile["money_columns"], ["Unit Cost", "Budget"])
        self.assertEqual(excel_profile["business_role"], "engineering_inventory")
        self.assertEqual(excel_profile["top_items"][:2], ["Pump A", "Valve B"])
        self.assertIn("Owner", excel_profile["header_fields"])
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
