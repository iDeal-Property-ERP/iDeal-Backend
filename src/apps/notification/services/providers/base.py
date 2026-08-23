from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PushMessage:
    token: str
    title: str
    body: str
    data: dict[str, str]
    replacement_key: str | None = None


class PushDeliveryError(Exception):
    """Raised when a push provider cannot deliver a message."""


class PushTokenInvalidError(PushDeliveryError):
    """Raised when a push provider reports that a device token is unusable."""


class PushProvider(ABC):
    """Normalized delivery interface shared by push gateways."""

    @abstractmethod
    def send(self, message: PushMessage) -> None:
        """Deliver a push message or raise a push delivery error."""
