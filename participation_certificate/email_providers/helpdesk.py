"""HelpDesk email provider implementation."""

from typing import Any

from pytanis.helpdesk import HelpDeskClient, Mail, MailClient

from participation_certificate import logger

from .base import EmailProvider


class HelpDeskProvider(EmailProvider):
    """Email provider using pytanis HelpDesk."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize HelpDesk provider.

        Args:
            config: Configuration with keys:
                - team_id: HelpDesk team ID
                - agent_id: HelpDesk agent ID (optional)
                - throttle_requests: Number of requests before throttling (default: 1)
                - throttle_period: Seconds to wait after throttle_requests (default: 10)
        """
        super().__init__(config)
        self.mail_client = MailClient()
        self.helpdesk_client = HelpDeskClient()

        # Set throttling if configured
        throttle_requests = self.config.get("throttle_requests", 1)
        throttle_period = self.config.get("throttle_period", 10)
        self.helpdesk_client.set_throttling(throttle_requests, throttle_period)

    def validate_config(self) -> None:
        """Validate HelpDesk configuration."""
        if not self.config.get("team_id"):
            raise ValueError("HelpDesk provider requires 'team_id' in configuration")

    def send(self, mail: Mail, dry_run: bool = False) -> tuple[Any, list[str]]:
        """Send email via HelpDesk.

        Args:
            mail: Email object with recipients, subject, body, etc.
            dry_run: If True, simulate sending without actually sending.

        Returns:
            Tuple of (responses, errors) from HelpDesk API.
        """
        # Ensure mail has required HelpDesk fields
        if not mail.team_id and self.config.get("team_id"):
            mail.team_id = self.config["team_id"]

        if not mail.agent_id and self.config.get("agent_id"):
            mail.agent_id = self.config["agent_id"]
        elif not mail.agent_id:
            # Use HelpDesk client's configured account as fallback
            mail.agent_id = self.helpdesk_client._config.HelpDesk.account

        # Set default status if not provided
        if not mail.status:
            mail.status = "closed"

        logger.info(
            f"{'[DRY RUN] ' if dry_run else ''}Sending email via HelpDesk to "
            f"{len(mail.recipients)} recipient(s): {mail.subject}"
        )

        try:
            responses, errors = self.mail_client.send(mail, dry_run=dry_run)
            if errors:
                logger.error(f"HelpDesk errors: {errors}")
            return responses, errors
        except Exception as e:
            error_msg = f"Failed to send via HelpDesk: {str(e)}"
            logger.error(error_msg)
            return None, [error_msg]

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "HelpDesk"
