_STATUS_UA: dict[str, str] = {
    "not_found": "Не знайдено",
    "created": "Запис створено",
    "booked": "Заброньовано",
    "received": "Прийнято",
    "in_origin_terminal": "На терміналі відправлення",
    "departed": "Відправлено",
    "in_transit": "У транзиті",
    "arrived": "Прибуло",
    "customs": "Митне оформлення",
    "ready_for_pickup": "Готово до видачі",
    "delivered": "Доставлено",
    "container_picked_up": "Контейнер забрано",
    "container_returned": "Контейнер повернуто",
    "exception": "Затримка або проблема",
    "unknown": "Статус невідомий",
}


def translate_status(normalized_status: str | None) -> str | None:
    if not normalized_status:
        return None
    return _STATUS_UA.get(normalized_status)
