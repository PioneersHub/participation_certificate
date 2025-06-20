"""Email provider factory and registry."""

from typing import Any

from participation_certificate import logger

from .base import EmailProvider
from .brevo import BrevoProvider
from .helpdesk import HelpDeskProvider

# Registry of available email providers
PROVIDERS: dict[str, type[EmailProvider]] = {
    "helpdesk": HelpDeskProvider,
    "brevo": BrevoProvider,
}


def get_email_provider(provider_name: str, config: dict[str, Any]) -> EmailProvider:
    """Get an email provider instance based on configuration.

    Args:
        provider_name: Name of the provider (e.g., "helpdesk", "brevo").
        config: Provider-specific configuration dictionary.

    Returns:
        Configured email provider instance.

    Raises:
        ValueError: If provider name is not recognized.
    """
    if provider_name not in PROVIDERS:
        available = ", ".join(sorted(PROVIDERS.keys()))
        raise ValueError(
            f"Unknown email provider: {provider_name}. Available providers: {available}"
        )

    provider_class = PROVIDERS[provider_name]
    logger.info(f"Initializing {provider_name} email provider")

    try:
        return provider_class(config)
    except Exception as e:
        logger.error(f"Failed to initialize {provider_name} provider: {e}")
        raise


def register_provider(name: str, provider_class: type[EmailProvider]) -> None:
    """Register a new email provider.

    Args:
        name: Name to register the provider under.
        provider_class: The provider class (must inherit from EmailProvider).
    """
    if not issubclass(provider_class, EmailProvider):
        raise TypeError(f"{provider_class} must inherit from EmailProvider")

    PROVIDERS[name] = provider_class
    logger.info(f"Registered email provider: {name}")


__all__ = ["EmailProvider", "get_email_provider", "register_provider"]
