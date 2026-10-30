"""Docling native conversion probe. A rejected format is an explicit result."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time
import uuid

from docling.document_converter import DocumentConverter


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    args = ap.parse_args()
    out = Path(".m1-local/crossformat-docling") / uuid.uuid4().hex
    out.mkdir(parents=True)
    raw = args.source.read_bytes()
    record = {"sourceDigest": hashlib.sha256(raw).hexdigest(), "name": args.source.name,
              "parserVersion": importlib.metadata.version("docling-slim"),
              "derivedConversion": False}
    started = time.monotonic()
    try:
        options = {}
        if args.source.suffix.lower() == ".pdf":
            from docling.document_converter import PdfFormatOption
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
            profile = PdfPipelineOptions(do_ocr=False, do_table_structure=False,
                      accelerator_options=AcceleratorOptions(num_threads=2, device=AcceleratorDevice.CPU))
            options[InputFormat.PDF] = PdfFormatOption(pipeline_options=profile)
            record["profile"] = {"ocr": False, "tableStructure": False, "device": "cpu", "threads": 2}
        record["execution"] = "STARTED"
        (out / "report.json").write_text(json.dumps(record, indent=2))
        result = DocumentConverter(format_options=options).convert(args.source.resolve())
        record.update(execution="COMPLETED", parseStatus=str(result.status),
                      document=result.document.export_to_dict())
    except Exception as exc:
        record.update(execution="FAILED", errorType=type(exc).__name__, error=str(exc))
    record["elapsedSeconds"] = round(time.monotonic() - started, 3)
    (out / "report.json").write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print(record["execution"], "Evidence:", out)


if __name__ == "__main__":
    main()
