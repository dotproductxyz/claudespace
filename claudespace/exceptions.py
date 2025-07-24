"""Custom exceptions for claudespace."""


class ClaudespaceError(Exception):
    """Base exception for claudespace."""

    pass


class WorkspaceNotFoundError(ClaudespaceError):
    """Raised when a workspace doesn't exist."""

    pass


class WorkspaceExistsError(ClaudespaceError):
    """Raised when trying to create a workspace that already exists."""

    pass


class ConfigError(ClaudespaceError):
    """Raised when there's an issue with the configuration."""

    pass


class DockerError(ClaudespaceError):
    """Raised when there's an issue with Docker operations."""

    pass
