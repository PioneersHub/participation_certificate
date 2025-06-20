"""Base class for email providers."""

from abc import ABC, abstractmethod
from typing import Any

from pytanis.helpdesk import Mail


class EmailProvider(ABC):
    """Abstract base class for email providers."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the email provider with configuration.

        Args:
            config: Provider-specific configuration dictionary.
        """
        self.config = config
        self.validate_config()

    @abstractmethod
    def validate_config(self) -> None:
        """Validate the provider configuration.

        Raises:
            ValueError: If required configuration is missing or invalid.
        """
        pass

    @abstractmethod
    def send(self, mail: Mail, dry_run: bool = False) -> tuple[Any, list[str]]:
        """Send an email.

        Args:
            mail: Email object containing recipients, subject, body, etc.
            dry_run: If True, simulate sending without actually sending.

        Returns:
            Tuple of (response, errors) where:
                - response: Provider-specific response object/dict
                - errors: List of error messages if any
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name for logging/debugging."""
        pass
