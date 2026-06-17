import pytest

from app.core.translator import translate_status


@pytest.mark.parametrize(
    "status,expected",
    [
        ("departed", "Вантаж або судно/рейс відправлено."),
        ("in_transit", "Вантаж у транзиті."),
        ("arrived", "Вантаж прибув у порт / аеропорт."),
        ("delivered", "Доставлено / видано."),
        ("container_picked_up", "Порожній або завантажений контейнер забраний."),
        ("container_returned", "Порожній контейнер повернуто."),
        ("in_origin_terminal", "Вантаж на origin terminal."),
        ("received", "Вантаж прийнято складом / авіалінією."),
        ("customs", "Митні процедури."),
        ("ready_for_pickup", "Готовий до отримання."),
        ("exception", "Проблема, затримка, hold, failed event."),
        ("not_found", "Номер валідний, але tracking-дані не знайдено."),
        ("created", "Запис або booking створено."),
        ("booked", "Вантаж заброньований у перевізника."),
        ("unknown", "Статус не вдалося класифікувати."),
    ],
)
def test_known_statuses_translated(status: str, expected: str) -> None:
    assert translate_status(status) == expected


def test_unknown_status_returns_none() -> None:
    assert translate_status("some_future_status") is None


def test_none_input_returns_none() -> None:
    assert translate_status(None) is None


def test_empty_string_returns_none() -> None:
    assert translate_status("") is None
