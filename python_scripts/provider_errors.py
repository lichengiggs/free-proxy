from __future__ import annotations


class ProviderError(RuntimeError):
    pass


class ProviderHTTPError(ProviderError):
    def __init__(self, *, message: str, status: int, category: str) -> None:
        super().__init__(message)
        self.status = status
        self.category = category
