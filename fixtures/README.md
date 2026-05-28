# Fixtures

This directory will hold test documents and evaluation datasets.

Planned fixture groups:

- `basic_docs`: TXT, DOCX, PDF, XLSX, and PPTX files for parser and FTS checks.
- `bad_docs`: damaged, empty, encrypted, and unsupported files.
- `engineering_project`: related documents for profile, entity, and related-file evaluation.
- `versions`: draft, revised, final, and duplicate files.
- `privacy`: files containing sensitive fields for redaction and audit tests.
- `large_scale`: generated metadata for scan and UI performance tests.
- `graph`: clustered and isolated documents for graph validation.

Do not place private real-world documents in this directory.

Generate the basic fixture set with:

```powershell
python scripts/generate-basic-fixtures.py
```

