"""Exceptions raised by the dreamboxapi client."""


class DreamboxError(Exception):
    """Base exception for all dreamboxapi errors."""


class DreamboxConnectionError(DreamboxError):
    """The dreambox could not be reached."""


class DreamboxAuthenticationError(DreamboxError):
    """The dreambox rejected the configured credentials."""


class DreamboxProtocolError(DreamboxError):
    """The dreambox returned a response the client cannot use."""
