from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "fixtures" / "basic_docs"
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)

DOCUMENT_TEXT = {
    "txt": "Alpha Project kickoff notes for DocGraph local search.\nBudget owner: North Center.\n",
    "docx": "Alpha Project contract summary. Device list includes cameras and switches.",
    "xlsx": "Alpha Project budget sheet with cameras, switches, and server quantities.",
    "pptx": "Alpha Project status deck. Search should find roadmap and delivery notes.",
    "pdf": "Alpha Project PDF brief for search fixtures.",
}


def main() -> None:
    if FIXTURE_DIR.exists():
        shutil.rmtree(FIXTURE_DIR)
    FIXTURE_DIR.mkdir(parents=True)

    write_txt(FIXTURE_DIR / "alpha_notes.txt")
    write_docx(FIXTURE_DIR / "alpha_contract.docx", DOCUMENT_TEXT["docx"])
    write_xlsx(FIXTURE_DIR / "alpha_budget.xlsx")
    write_pptx(FIXTURE_DIR / "alpha_status.pptx", DOCUMENT_TEXT["pptx"])
    write_pdf(FIXTURE_DIR / "alpha_brief.pdf", DOCUMENT_TEXT["pdf"])
    (FIXTURE_DIR / "empty.txt").write_text("", encoding="utf-8")
    (FIXTURE_DIR / "bad_file.bin").write_bytes(b"not a valid office document\n")
    write_expected_search(FIXTURE_DIR / "expected_search.json")
    write_readme(FIXTURE_DIR / "README.md")
    print(f"Generated basic fixtures in {FIXTURE_DIR}")


def write_txt(path: Path) -> None:
    path.write_text(DOCUMENT_TEXT["txt"], encoding="utf-8")


def write_docx(path: Path, body: str) -> None:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>{escape(body)}</w:t></w:r></w:p>
  </w:body>
</w:document>
"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        write_zip_text(archive, "[Content_Types].xml", DOCX_CONTENT_TYPES)
        write_zip_text(archive, "_rels/.rels", DOCX_RELS)
        write_zip_text(archive, "word/document.xml", document_xml)


def write_xlsx(path: Path) -> None:
    sheet_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t>Item</t></is></c>
      <c r="B1" t="inlineStr"><is><t>Quantity</t></is></c>
    </row>
    <row r="2">
      <c r="A2" t="inlineStr"><is><t>Alpha Project camera</t></is></c>
      <c r="B2"><v>12</v></c>
    </row>
    <row r="3">
      <c r="A3" t="inlineStr"><is><t>Switch</t></is></c>
      <c r="B3"><v>4</v></c>
    </row>
  </sheetData>
</worksheet>
"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        write_zip_text(archive, "[Content_Types].xml", XLSX_CONTENT_TYPES)
        write_zip_text(archive, "_rels/.rels", XLSX_RELS)
        write_zip_text(archive, "xl/workbook.xml", XLSX_WORKBOOK)
        write_zip_text(archive, "xl/_rels/workbook.xml.rels", XLSX_WORKBOOK_RELS)
        write_zip_text(archive, "xl/worksheets/sheet1.xml", sheet_xml)


def write_pptx(path: Path, body: str) -> None:
    slide_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr/>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>{escape(body)}</a:t></a:r></a:p></p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>
"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        write_zip_text(archive, "[Content_Types].xml", PPTX_CONTENT_TYPES)
        write_zip_text(archive, "_rels/.rels", PPTX_RELS)
        write_zip_text(archive, "ppt/presentation.xml", PPTX_PRESENTATION)
        write_zip_text(archive, "ppt/_rels/presentation.xml.rels", PPTX_PRESENTATION_RELS)
        write_zip_text(archive, "ppt/slides/slide1.xml", slide_xml)


def write_zip_text(archive: zipfile.ZipFile, name: str, text: str) -> None:
    info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, text.encode("utf-8"))


def write_pdf(path: Path, body: str) -> None:
    stream = f"BT /F1 12 Tf 72 720 Td ({escape_pdf(body)}) Tj ET"
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >> endobj\n",
        f"4 0 obj << /Length {len(stream.encode('ascii'))} >> stream\n{stream}\nendstream endobj\n".encode(
            "ascii"
        ),
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for item in objects:
        offsets.append(len(output))
        output.extend(item)
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer << /Root 1 0 R /Size {len(objects) + 1} >>\nstartxref\n{xref_offset}\n%%EOF\n".encode(
            "ascii"
        )
    )
    path.write_bytes(bytes(output))


def escape_pdf(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_expected_search(path: Path) -> None:
    payload = {
        "version": 1,
        "fixture_group": "basic_docs",
        "queries": [
            {
                "query": "alpha project",
                "expected_files": [
                    "alpha_notes.txt",
                    "alpha_contract.docx",
                    "alpha_budget.xlsx",
                    "alpha_status.pptx",
                    "alpha_brief.pdf",
                ],
                "purpose": "Common term appears across all parseable fixture documents.",
            },
            {
                "query": "camera",
                "expected_files": ["alpha_contract.docx", "alpha_budget.xlsx"],
                "purpose": "Device term appears in office document fixtures.",
            },
            {
                "query": "roadmap",
                "expected_files": ["alpha_status.pptx"],
                "purpose": "Presentation-specific query.",
            },
        ],
        "non_parseable_files": ["empty.txt", "bad_file.bin"],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_readme(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Basic Docs Fixtures",
                "",
                "Generated by `python scripts/generate-basic-fixtures.py`.",
                "",
                "These files are synthetic and safe to commit. They are for parser, scanner, and search tests.",
                "",
                "- `alpha_notes.txt`",
                "- `alpha_contract.docx`",
                "- `alpha_budget.xlsx`",
                "- `alpha_status.pptx`",
                "- `alpha_brief.pdf`",
                "- `empty.txt`",
                "- `bad_file.bin`",
                "- `expected_search.json`",
                "",
            ]
        ),
        encoding="utf-8",
    )


DOCX_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""

DOCX_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

XLSX_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
"""

XLSX_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""

XLSX_WORKBOOK = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Budget" sheetId="1" r:id="rId1"/></sheets>
</workbook>
"""

XLSX_WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>
"""

PPTX_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
</Types>
"""

PPTX_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>
"""

PPTX_PRESENTATION = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
</p:presentation>
"""

PPTX_PRESENTATION_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>
"""


if __name__ == "__main__":
    main()
