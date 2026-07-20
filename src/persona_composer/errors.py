"""Composer errors."""


class CompositionError(Exception):
    """Base error for persona composer failures."""


class ValidationError(CompositionError):
    """Build-time validation failure; never render a known-bad prompt."""

    def __init__(self, message: str, *, errors: list[str] | None = None) -> None:
        self.errors = errors or [message]
        super().__init__(message if errors is None else "; ".join(self.errors))
