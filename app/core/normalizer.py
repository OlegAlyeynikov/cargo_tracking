import logging

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_AIR_STATUS_MAP: dict[str, str] = {
    "booking created": "created",
    "booked": "booked",
    "cargo received": "received",
    "rcs": "received",
    "shipment received": "received",
    "received from shipper": "received",
    "accepted": "in_origin_terminal",
    "acceptance": "in_origin_terminal",
    "in_origin_terminal": "in_origin_terminal",
    "origin terminal": "in_origin_terminal",
    "departed": "departed",
    "dep": "departed",
    "departure": "departed",
    "flight departed": "departed",
    "manifested": "departed",
    "man": "in_transit",
    "transit": "in_transit",
    "in transit": "in_transit",
    "transfer": "in_transit",
    "transshipment": "in_transit",
    "arrived": "arrived",
    "arr": "arrived",
    "arrival": "arrived",
    "rcf": "arrived",
    "flight arrived": "arrived",
    "customs": "customs",
    "cleared customs": "customs",
    "customs cleared": "customs",
    "ready for pickup": "ready_for_pickup",
    "nfd": "ready_for_pickup",
    "notification": "ready_for_pickup",
    "available for pickup": "ready_for_pickup",
    "delivered": "delivered",
    "dlv": "delivered",
    "delivery": "delivered",
    "pod": "delivered",
    "not found": "not_found",
    "no data": "not_found",
    "foh": "in_origin_terminal",
    "fwd": "in_transit",
    "tfr": "in_transit",
}

_SEA_STATUS_MAP: dict[str, str] = {
    "gate out empty": "container_picked_up",
    "empty pickup": "container_picked_up",
    "empty released": "container_picked_up",
    "container picked up": "container_picked_up",
    "gate in": "in_origin_terminal",
    "full in": "in_origin_terminal",
    "loaded on vessel": "departed",
    "load": "departed",
    "vessel departure": "departed",
    "departure": "departed",
    "departed": "departed",
    "transshipment": "in_transit",
    "transship": "in_transit",
    "in transit": "in_transit",
    "vessel arrival": "arrived",
    "arrival": "arrived",
    "arrived": "arrived",
    "discharged": "arrived",
    "discharge": "arrived",
    "available": "ready_for_pickup",
    "customs": "customs",
    "customs cleared": "customs",
    "delivered": "delivered",
    "delivery": "delivered",
    "empty returned": "container_returned",
    "gate out full": "delivered",
    "not found": "not_found",
    "no data": "not_found",
    "hold": "exception",
    "exception": "exception",
    "delay": "exception",
    "rolled": "exception",
}

_openrouter_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI | None:
    global _openrouter_client
    if not settings.openrouter_api_key:
        return None
    if _openrouter_client is None:
        raw: AsyncOpenAI = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        _openrouter_client = _wrap_with_langsmith(raw)
    return _openrouter_client


def _wrap_with_langsmith(client: AsyncOpenAI) -> AsyncOpenAI:
    if not (settings.langsmith_tracing and settings.langsmith_api_key):
        return client
    try:
        import os

        from langsmith.wrappers import wrap_openai

        os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
        os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)
        logger.info("LangSmith tracing enabled (project=%s)", settings.langsmith_project)
        return wrap_openai(client)  # type: ignore[return-value]
    except ImportError:
        logger.warning(
            "LANGSMITH_TRACING=true but langsmith is not installed — run: uv add langsmith"
        )
        return client


def normalize_status(raw_status: str, shipment_type: str) -> str:
    key = raw_status.lower().strip()
    status_map = _AIR_STATUS_MAP if shipment_type == "air_awb" else _SEA_STATUS_MAP
    for phrase, normalized in status_map.items():
        if phrase in key:
            return normalized
    return "unknown"


async def normalize_status_with_ai_fallback(raw_status: str, shipment_type: str) -> str:
    normalized = normalize_status(raw_status, shipment_type)
    if normalized != "unknown":
        return normalized

    client = _get_client()
    if client is None:
        logger.warning(
            "OpenRouter API key not set, cannot use AI fallback for status normalization"
        )
        return "unknown"

    prompt = _build_normalization_prompt(raw_status, shipment_type)
    try:
        response = await client.chat.completions.create(
            model=settings.openrouter_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=settings.openrouter_max_tokens,
            temperature=settings.openrouter_temperature,
        )
        result = response.choices[0].message.content or ""
        return result.strip().lower().replace('"', "").replace("'", "")
    except Exception as exc:
        logger.warning("AI status normalization failed: %s", exc)
        return "unknown"


def _build_normalization_prompt(raw_status: str, shipment_type: str) -> str:
    valid_statuses = (
        "created, booked, received, in_origin_terminal, departed, in_transit, "
        "arrived, customs, ready_for_pickup, delivered, container_picked_up, "
        "container_returned, exception, not_found, unknown"
    )
    cargo_kind = "air cargo AWB" if shipment_type == "air_awb" else "sea container"
    return (
        f"Map this {cargo_kind} tracking status to ONE of the normalized values.\n"
        f'Raw status: "{raw_status}"\n'
        f"Valid values: {valid_statuses}\n"
        f"Reply with only the normalized status value, nothing else."
    )
