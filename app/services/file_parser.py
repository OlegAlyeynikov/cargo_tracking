import csv
import io
import logging

import openpyxl

from app.models.request import ShipmentInput

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
_REQUIRED_COLUMN = "number"
_OPTIONAL_COLUMNS = {"id", "type", "carrier", "comment"}


def parse_file(content: bytes, filename: str) -> list[ShipmentInput]:
    """Parse CSV or Excel file into a list of ShipmentInput objects.

    Required column: number
    Optional columns: id, type, carrier, comment

    If 'id' is missing, rows are auto-numbered as row-1, row-2, etc.
    """
    ext = _extension(filename)
    if ext not in _SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. Supported formats: CSV (.csv), Excel (.xlsx)"
        )

    rows = _parse_csv(content) if ext == ".csv" else _parse_excel(content)

    if not rows:
        raise ValueError("File is empty or contains no data rows")

    _validate_headers(rows[0].keys(), filename)

    shipments: list[ShipmentInput] = []
    for i, row in enumerate(rows, start=1):
        number = row.get("number", "").strip()
        if not number:
            logger.warning("Row %d skipped: missing 'number' value", i)
            continue
        shipments.append(ShipmentInput(
            id=row.get("id", "").strip() or f"row-{i}",
            number=number,
            type=row.get("type", "").strip() or None,
            carrier=row.get("carrier", "").strip() or None,
            comment=row.get("comment", "").strip() or None,
        ))

    if not shipments:
        raise ValueError("No valid rows found — every row is missing the 'number' column value")

    return shipments


def _parse_csv(content: bytes) -> list[dict[str, str]]:
    text = content.decode("utf-8-sig")  # utf-8-sig strips BOM if present
    reader = csv.DictReader(io.StringIO(text))
    return [_normalize_keys(row) for row in reader]


def _parse_excel(content: bytes) -> list[dict[str, str]]:
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    headers = [str(cell).strip().lower() if cell is not None else "" for cell in rows[0]]

    result: list[dict[str, str]] = []
    for row in rows[1:]:
        if all(cell is None for cell in row):
            continue
        result.append({
            headers[i]: str(cell).strip() if cell is not None else ""
            for i, cell in enumerate(row)
            if i < len(headers) and headers[i]
        })

    return result


def _normalize_keys(row: dict) -> dict[str, str]:
    return {k.strip().lower(): str(v).strip() if v is not None else "" for k, v in row.items()}


def _validate_headers(keys: any, filename: str) -> None:
    normalized = {k.strip().lower() for k in keys}
    if _REQUIRED_COLUMN not in normalized:
        raise ValueError(
            f"File '{filename}' is missing required column 'number'. "
            f"Found columns: {', '.join(sorted(normalized)) or '(none)'}"
        )


def _extension(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot != -1 else ""
