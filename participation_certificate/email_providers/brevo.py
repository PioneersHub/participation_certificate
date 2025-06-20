"""Brevo (formerly SendinBlue) email provider implementation."""

import json
from http import HTTPStatus
from pathlib import Path
from typing import Any

import requests
from pytanis.helpdesk import Mail

from participation_certificate import logger

from .base import EmailProvider


class BrevoProvider(EmailProvider):
    """Email provider using Brevo (formerly SendinBlue) API."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize Brevo provider.

        Args:
            config: Configuration with keys:
                - api_key: Brevo API key (optional if api_key_path is provided)
                - api_key_path: Path to file containing API key
                - sender_name: Name of the sender
                - sender_email: Email address of the sender
        """
        super().__init__(config)
        self.api_key = self._get_api_key()
        self.sender_name = self.config["sender_name"]
        self.sender_email = self.config["sender_email"]
        self.api_url = "https://api.brevo.com/v3/smtp/email"

    def _get_api_key(self) -> str:
        """Get API key from config or file."""
        if self.config.get("api_key"):
            return self.config["api_key"]

        api_key_path = self.config.get("api_key_path")
        if api_key_path:
            path = Path(api_key_path)
            # Relative to project root if not absolute
            key_file = path if path.is_absolute() else Path(__file__).parents[2] / api_key_path

            if key_file.exists():
                return key_file.read_text().strip()
            else:
                raise ValueError(f"API key file not found: {key_file}")

        raise ValueError("Brevo provider requires either 'api_key' or 'api_key_path'")

    def validate_config(self) -> None:
        """Validate Brevo configuration."""
        required = ["sender_name", "sender_email"]
        missing = [key for key in required if not self.config.get(key)]

        if missing:
            raise ValueError(f"Brevo provider requires: {', '.join(missing)}")

        # Check that we can get an API key
        if not self.config.get("api_key") and not self.config.get("api_key_path"):
            raise ValueError("Brevo provider requires either 'api_key' or 'api_key_path'")

    def send(self, mail: Mail, dry_run: bool = False) -> tuple[Any, list[str]]:
        """Send email via Brevo API.

        Args:
            mail: Email object with recipients, subject, body, etc.
            dry_run: If True, simulate sending without actually sending.

        Returns:
            Tuple of (response, errors) where:
                - response: Brevo API response dict or None
                - errors: List of error messages if any
        """
        # Prepare headers
        headers = {
            "accept": "application/json",
            "api-key": self.api_key,
            "content-type": "application/json",
        }

        # Prepare payload
        payload = {
            "sender": {"name": self.sender_name, "email": self.sender_email},
            "to": [
                {
                    "email": recipient.email,
                    "name": recipient.name if recipient.name else recipient.email,
                }
                for recipient in mail.recipients
            ],
            "subject": mail.subject,
            "textContent": mail.text,
        }

        # Add HTML content if available
        if hasattr(mail, "html") and mail.html:
            payload["htmlContent"] = mail.html

        logger.info(
            f"{'[DRY RUN] ' if dry_run else ''}Sending email via Brevo to "
            f"{len(mail.recipients)} recipient(s): {mail.subject}"
        )

        if dry_run:
            logger.info(f"Dry run payload: {json.dumps(payload, indent=2)}")
            return {"message": "Dry run - email not sent", "payload": payload}, []

        errors: list[str] = []
        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                data=json.dumps(payload),
                timeout=30,
            )

            # Brevo returns 201 Created for successful email sends
            if response.status_code == HTTPStatus.CREATED:
                logger.info("Email sent successfully via Brevo!")
                return response.json(), errors
            else:
                error_msg = (
                    f"Failed to send email via Brevo. "
                    f"Status code: {response.status_code}, "
                    f"Response: {response.text}"
                )
                logger.error(error_msg)
                errors.append(error_msg)
                return None, errors

        except requests.exceptions.Timeout:
            error_msg = "Brevo API request timed out"
            logger.error(error_msg)
            return None, [error_msg]
        except requests.exceptions.RequestException as e:
            error_msg = f"Brevo API request failed: {str(e)}"
            logger.error(error_msg)
            return None, [error_msg]
        except Exception as e:
            error_msg = f"Unexpected error sending via Brevo: {str(e)}"
            logger.error(error_msg)
            return None, [error_msg]

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "Brevo"
