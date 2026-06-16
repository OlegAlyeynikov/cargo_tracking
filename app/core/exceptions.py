class TrackingError(Exception):
    def __init__(self, code: str, message: str, source: str = "") -> None:
        self.code = code
        self.message = message
        self.source = source
        super().__init__(message)


class InvalidFormatError(TrackingError):
    def __init__(self, number: str) -> None:
        super().__init__(
            code="INVALID_FORMAT",
            message=f"Number '{number}' does not match AWB or container number format",
        )


class NotFoundError(TrackingError):
    def __init__(self, number: str, source: str = "") -> None:
        super().__init__(
            code="NOT_FOUND",
            message=f"Tracking data not found for '{number}'",
            source=source,
        )


class SourceUnavailableError(TrackingError):
    def __init__(self, source: str, reason: str = "") -> None:
        super().__init__(
            code="SOURCE_UNAVAILABLE",
            message=f"Source '{source}' is temporarily unavailable. {reason}".strip(),
            source=source,
        )


class TimeoutError(TrackingError):
    def __init__(self, source: str) -> None:
        super().__init__(
            code="TIMEOUT",
            message=f"Request to '{source}' timed out",
            source=source,
        )


class CaptchaRequiredError(TrackingError):
    def __init__(self, source: str) -> None:
        super().__init__(
            code="CAPTCHA_REQUIRED",
            message=f"Source '{source}' requires CAPTCHA; automatic extraction is not possible",
            source=source,
        )


class LoginRequiredError(TrackingError):
    def __init__(self, source: str) -> None:
        super().__init__(
            code="LOGIN_REQUIRED",
            message=f"Source '{source}' requires login or closed account access",
            source=source,
        )


class ParsingFailedError(TrackingError):
    def __init__(self, source: str, detail: str = "") -> None:
        super().__init__(
            code="PARSING_FAILED",
            message=f"Received response from '{source}' but could not parse data. {detail}".strip(),
            source=source,
        )
