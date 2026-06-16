import json
import re
from pathlib import Path

from app.models.response import CarrierInfo, DetectedInfo

_AWB_PATTERN = re.compile(r"^\d{3}-?\d{8}$")
_CONTAINER_PATTERN = re.compile(r"^[A-Z]{4}\d{7}$")

_PREFIXES: dict[str, dict[str, str]] = json.loads(
    (Path(__file__).parent.parent.parent / "data" / "awb_prefixes.json").read_text()
)

_CONTAINER_OWNERS: dict[str, str] = {
    "MSKU": "Maersk",
    "MAEU": "Maersk",
    "MAEI": "Maersk",
    "MSCU": "MSC",
    "CMAU": "CMA CGM",
    "HLCU": "Hapag-Lloyd",
    "OOLU": "OOCL",
    "EITU": "Evergreen",
    "YMLU": "Yang Ming",
    "CAIU": "COSCO",
    "CBHU": "COSCO",
    "CCLU": "COSCO",
    "CXDU": "COSCO",
    "FCIU": "COSCO",
    "TRHU": "Triton International",
    "TLLU": "Triton International",
    "TTNU": "Triton International",
    "TPHU": "Triton International",
    "TGHU": "Triton International",
    "TCKU": "Triton International",
    "TOLU": "Touax",
    "UETU": "Textainer",
    "TEXU": "Textainer",
    "CRXU": "CAI International",
    "CARU": "CAI International",
    "BSIU": "Beacon Intermodal",
    "LGHU": "Seaco",
}

_ISO6346_WEIGHTS = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512]
_CHAR_VALUES = {c: i + (i // 11) for i, c in enumerate("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")}


def _iso6346_check_digit(number: str) -> bool:
    """Validate ISO 6346 check digit for container numbers (4 letters + 6 digits + 1 check)."""
    if len(number) != 11:
        return False
    total = sum(_CHAR_VALUES.get(c, 0) * _ISO6346_WEIGHTS[i] for i, c in enumerate(number[:10]))
    expected = total % 11 % 10
    try:
        return int(number[10]) == expected
    except ValueError:
        return False


def _normalize_input(number: str) -> str:
    return number.strip().upper().replace(" ", "")


def detect(number: str) -> DetectedInfo:
    normalized = _normalize_input(number)
    warnings: list[str] = []

    if _AWB_PATTERN.match(normalized):
        canonical = normalized if "-" in normalized else f"{normalized[:3]}-{normalized[3:]}"
        prefix = canonical[:3]
        serial = canonical[4:]  # 8 digits after the dash
        awb_warnings: list[str] = []
        if len(serial) == 8 and serial.isdigit():
            expected = int(serial[:7]) % 7
            if int(serial[7]) != expected:
                awb_warnings.append("invalid_check_digit")
        carrier_data = _PREFIXES.get(prefix)
        carrier = (
            CarrierInfo(name=carrier_data["name"], code=carrier_data["code"], source="awb_prefix")
            if carrier_data
            else CarrierInfo(source="awb_prefix")
        )
        return DetectedInfo(type="air_awb", normalized_number=canonical, carrier=carrier, warnings=awb_warnings)

    if _CONTAINER_PATTERN.match(normalized):
        if not _iso6346_check_digit(normalized):
            warnings.append("invalid_check_digit")
        owner_code = normalized[:4]
        carrier_name = _CONTAINER_OWNERS.get(owner_code)
        carrier = CarrierInfo(name=carrier_name, code=owner_code, source="bic_prefix")
        return DetectedInfo(type="sea_container", normalized_number=normalized, carrier=carrier, warnings=warnings)

    return DetectedInfo(type="unknown", normalized_number=normalized, carrier=None)
