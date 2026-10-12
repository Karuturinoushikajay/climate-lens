from __future__ import annotations


class AppError(Exception):
    """An error that is safe to show to API clients."""

    def __init__(self, status_code: int, code: str, message: str, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}


class WeatherProviderError(AppError):
    pass
