import pytest

from app.core.normalizer import normalize_status


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Cargo received", "received"),
        ("RCS", "received"),
        ("Departed from origin airport", "departed"),
        ("DEP", "departed"),
        ("In transit to destination", "in_transit"),
        ("MAN", "in_transit"),
        ("Flight arrived", "arrived"),
        ("ARR", "arrived"),
        ("Ready for pickup", "ready_for_pickup"),
        ("NFD", "ready_for_pickup"),
        ("Delivered to consignee", "delivered"),
        ("DLV", "delivered"),
        ("Booking created", "created"),
        ("Not found", "not_found"),
    ],
)
def test_air_awb_status_normalization(raw: str, expected: str) -> None:
    assert normalize_status(raw, "air_awb") == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Gate out empty", "container_picked_up"),
        ("Empty pickup", "container_picked_up"),
        ("Gate in", "in_origin_terminal"),
        ("Loaded on vessel", "departed"),
        ("Vessel departure", "departed"),
        ("Transshipment", "in_transit"),
        ("Vessel arrival", "arrived"),
        ("Discharged", "arrived"),
        ("Available", "ready_for_pickup"),
        ("Customs cleared", "customs"),
        ("Delivered", "delivered"),
        ("Gate out full", "delivered"),
        ("Empty returned", "container_returned"),
        ("Hold", "exception"),
        ("Rolled", "exception"),
        ("Not found", "not_found"),
    ],
)
def test_sea_container_status_normalization(raw: str, expected: str) -> None:
    assert normalize_status(raw, "sea_container") == expected


def test_unknown_status_returns_unknown() -> None:
    assert (
        normalize_status("some completely unknown status XYZ", "air_awb") == "unknown"
    )
    assert (
        normalize_status("some completely unknown status XYZ", "sea_container")
        == "unknown"
    )


def test_case_insensitive() -> None:
    assert normalize_status("DEPARTED", "air_awb") == "departed"
    assert normalize_status("gate out empty", "sea_container") == "container_picked_up"
