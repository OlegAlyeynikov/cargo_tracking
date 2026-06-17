import pytest

from app.core.detector import detect


@pytest.mark.parametrize(
    "number,expected_type,expected_carrier_code",
    [
        ("080-38652331", "air_awb", "CX"),
        ("08038652331", "air_awb", "CX"),
        ("501-20285134", "air_awb", "EK"),
        ("020-26227456", "air_awb", "LH"),
        ("080-38652342", "air_awb", "CX"),
        ("080-38653985", "air_awb", "CX"),
    ],
)
def test_valid_awb_numbers(
    number: str, expected_type: str, expected_carrier_code: str
) -> None:
    result = detect(number)
    assert result.type == expected_type
    assert result.carrier is not None
    assert result.carrier.code == expected_carrier_code


@pytest.mark.parametrize(
    "number,expected_type",
    [
        ("MSKU1880987", "sea_container"),
        ("CAIU7533723", "sea_container"),
        ("TLLU4912250", "sea_container"),
        ("UETU5915440", "sea_container"),
        ("TRHU6714051", "sea_container"),
    ],
)
def test_valid_container_numbers(number: str, expected_type: str) -> None:
    result = detect(number)
    assert result.type == expected_type
    assert result.normalized_number == number.upper()


def test_maersk_container_has_carrier_name() -> None:
    result = detect("MSKU1880987")
    assert result.carrier is not None
    assert result.carrier.name == "Maersk"


def test_awb_normalized_with_dash() -> None:
    without = detect("08038652331")
    with_dash = detect("080-38652331")
    assert without.normalized_number == with_dash.normalized_number == "080-38652331"


def test_unknown_format_returns_unknown_type() -> None:
    result = detect("INVALID123")
    assert result.type == "unknown"


def test_empty_string_returns_unknown() -> None:
    result = detect("")
    assert result.type == "unknown"


def test_partial_awb_returns_unknown() -> None:
    result = detect("080-1234")
    assert result.type == "unknown"


def test_container_wrong_length_returns_unknown() -> None:
    result = detect("MSKU123456")
    assert result.type == "unknown"


def test_awb_with_letters_returns_unknown() -> None:
    result = detect("ABС-12345678")
    assert result.type == "unknown"


def test_unknown_awb_prefix_returns_no_carrier_name() -> None:
    result = detect("999-12345678")
    assert result.type == "air_awb"
    assert result.carrier is not None
    assert result.carrier.name is None


def test_lowercase_input_normalized() -> None:
    result = detect("msku1880987")
    assert result.type == "sea_container"
    assert result.normalized_number == "MSKU1880987"


def test_container_invalid_check_digit_warning() -> None:
    # MSKU1880987 has valid check digit 7; MSKU1880980 has wrong check digit
    result = detect("MSKU1880980")
    assert result.type == "sea_container"
    assert "invalid_check_digit" in result.warnings


def test_container_valid_check_digit_no_warning() -> None:
    result = detect("MSKU1880987")
    assert result.type == "sea_container"
    assert "invalid_check_digit" not in result.warnings


def test_awb_invalid_check_digit_warning() -> None:
    # 080-38652330: first 7 digits = 3865233, 3865233 % 7 = 1, so 0 is wrong
    result = detect("080-38652330")
    assert result.type == "air_awb"
    assert "invalid_check_digit" in result.warnings


def test_awb_valid_check_digit_no_warning() -> None:
    # 080-38652331: check digit = 1 (correct)
    result = detect("080-38652331")
    assert result.type == "air_awb"
    assert "invalid_check_digit" not in result.warnings
