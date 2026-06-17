_STATUS_UA: dict[str, str] = {
    "not_found": "Номер валідний, але tracking-дані не знайдено.",
    "created": "Запис або booking створено.",
    "booked": "Вантаж заброньований у перевізника.",
    "received": "Вантаж прийнято складом / авіалінією.",
    "in_origin_terminal": "Вантаж на origin terminal.",
    "departed": "Вантаж або судно/рейс відправлено.",
    "in_transit": "Вантаж у транзиті.",
    "arrived": "Вантаж прибув у порт / аеропорт.",
    "customs": "Митні процедури.",
    "ready_for_pickup": "Готовий до отримання.",
    "delivered": "Доставлено / видано.",
    "container_picked_up": "Порожній або завантажений контейнер забраний.",
    "container_returned": "Порожній контейнер повернуто.",
    "exception": "Проблема, затримка, hold, failed event.",
    "unknown": "Статус не вдалося класифікувати.",
}


def translate_status(normalized_status: str | None) -> str | None:
    if not normalized_status:
        return None
    return _STATUS_UA.get(normalized_status)
