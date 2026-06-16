import pytest

from app.core.translator import translate_status


@pytest.mark.parametrize("status,expected", [
    ("departed", "Відправлено"),
    ("in_transit", "У транзиті"),
    ("arrived", "Прибуло"),
    ("delivered", "Доставлено"),
    ("container_picked_up", "Контейнер забрано"),
    ("container_returned", "Контейнер повернуто"),
    ("in_origin_terminal", "На терміналі відправлення"),
    ("received", "Прийнято"),
    ("customs", "Митне оформлення"),
    ("ready_for_pickup", "Готово до видачі"),
    ("exception", "Затримка або проблема"),
    ("not_found", "Не знайдено"),
    ("created", "Запис створено"),
    ("booked", "Заброньовано"),
    ("unknown", "Статус невідомий"),
])
def test_known_statuses_translated(status: str, expected: str) -> None:
    assert translate_status(status) == expected


def test_unknown_status_returns_none() -> None:
    assert translate_status("some_future_status") is None


def test_none_input_returns_none() -> None:
    assert translate_status(None) is None


def test_empty_string_returns_none() -> None:
    assert translate_status("") is None
