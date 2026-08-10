class ChatError(Exception):
    """Base exception for chat-domain failures."""


class ChatUnavailableError(ChatError):
    """Raised when a listing cannot receive a new chat conversation."""


class ChatReadOnlyError(ChatError):
    """Raised when a chat side is not allowed to send messages."""
