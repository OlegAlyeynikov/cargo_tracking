import io

import openpyxl
import pytest

from app.services.file_parser import parse_file


def _csv(text: str) -> bytes:
    return text.strip().encode("utf-8")


def _xlsx(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --- CSV -------------------------------------------------------------------

def test_csv_minimal_columns() -> None:
    content = _csv("number\n501-20285134\nTLLU4912250")
    result = parse_file(content, "test.csv")
    assert len(result) == 2
    assert result[0].number == "501-20285134"
    assert result[0].id == "row-1"
    assert result[1].number == "TLLU4912250"
    assert result[1].id == "row-2"


def test_csv_all_columns() -> None:
    content = _csv("id,number,type,carrier,comment\nint-001,080-38652331,air_awb,CX,test")
    result = parse_file(content, "test.csv")
    assert len(result) == 1
    s = result[0]
    assert s.id == "int-001"
    assert s.number == "080-38652331"
    assert s.type == "air_awb"
    assert s.carrier == "CX"
    assert s.comment == "test"


def test_csv_case_insensitive_headers() -> None:
    content = _csv("Number,ID\nMSKU1880987,abc-1")
    result = parse_file(content, "test.csv")
    assert result[0].number == "MSKU1880987"
    assert result[0].id == "abc-1"


def test_csv_skips_rows_without_number() -> None:
    content = _csv("id,number\nok,501-20285134\nmissing,")
    result = parse_file(content, "test.csv")
    assert len(result) == 1
    assert result[0].number == "501-20285134"


def test_csv_bom_encoding() -> None:
    # Simulate a CSV exported by Excel which prepends a UTF-8 BOM
    content = "number\n501-20285134".encode("utf-8-sig")
    result = parse_file(content, "test.csv")
    assert result[0].number == "501-20285134"


def test_csv_missing_number_column_raises() -> None:
    content = _csv("id,carrier\ntest,CX")
    with pytest.raises(ValueError, match="missing required column 'number'"):
        parse_file(content, "test.csv")


def test_csv_empty_file_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        parse_file(b"number\n", "test.csv")


# --- Excel -----------------------------------------------------------------

def test_xlsx_minimal_columns() -> None:
    content = _xlsx([["number"], ["501-20285134"], ["TLLU4912250"]])
    result = parse_file(content, "test.xlsx")
    assert len(result) == 2
    assert result[0].number == "501-20285134"
    assert result[1].number == "TLLU4912250"


def test_xlsx_all_columns() -> None:
    content = _xlsx([
        ["id", "number", "type", "carrier", "comment"],
        ["int-001", "MSKU1880987", "sea_container", "MSKU", "test"],
    ])
    result = parse_file(content, "shipments.xlsx")
    s = result[0]
    assert s.id == "int-001"
    assert s.number == "MSKU1880987"
    assert s.type == "sea_container"


def test_xlsx_missing_number_column_raises() -> None:
    content = _xlsx([["id", "carrier"], ["x", "CX"]])
    with pytest.raises(ValueError, match="missing required column 'number'"):
        parse_file(content, "test.xlsx")


def test_xlsx_skips_empty_rows() -> None:
    content = _xlsx([["number"], ["501-20285134"], [None], ["TLLU4912250"]])
    result = parse_file(content, "test.xlsx")
    assert len(result) == 2


# --- Unsupported format ----------------------------------------------------

def test_unsupported_extension_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported file type"):
        parse_file(b"data", "shipments.txt")


def test_no_extension_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported file type"):
        parse_file(b"data", "shipments")
