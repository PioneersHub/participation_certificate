"""Thin Mailgun REST client for branded certificate-delivery emails.

Mirrors the pattern used in `conference_ticket_distribute/src/conference_tickets/integrations/mailgun/`.
We keep this in one small module rather than introducing a provider abstraction
— Mailgun is the only delivery transport.

Config (under `mailgun:` in config.yaml / config_local.yaml):

    domain: "mg.pycon.de"          # Mailgun sending domain
    region: "eu"                    # "eu" or "us"
    from_name: "PyCon DE & PyData 2026"
    from_email: "certificates@pycon.de"
    api_key_path: "_secret/mailgun_key"
    rate_limit_per_sec: 5

The API key file is a one-line plaintext file, read once at client construction.
"""

import time
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

import httpx

from participation_certificate import PROJECT_DIR, conf, logger

_EU_HOST = "https://api.eu.mailgun.net"
_US_HOST = "https://api.mailgun.net"
_HTTP_2XX = 2


@dataclass
class MailgunSendError(RuntimeError):
    """Raised when Mailgun returns a non-2xx response after the retry budget is spent."""

    status_code: int
    body: str

    def __str__(self) -> str:
        return f"Mailgun HTTP {self.status_code}: {self.body[:300]}"


class _RateLimiter:
    """Single-token rate limiter — calls `wait()` block until the per-second budget allows a send."""

    def __init__(self, per_second: float):
        self._min_interval = 1.0 / per_second if per_second > 0 else 0.0
        self._last = 0.0

    def wait(self) -> None:
        if self._min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last = time.monotonic()


class MailgunClient:
    """Send branded HTML+text emails with PDF attachments via the Mailgun v3 API."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        api_key: str,
        domain: str,
        from_header: str,
        host: str,
        rate_limit_per_sec: float = 5.0,
        timeout: float = 30.0,
    ):
        self.domain = domain
        self.from_header = from_header
        self.host = host
        self._endpoint = f"{host.rstrip('/')}/v3/{domain}/messages"
        self._rate_limiter = _RateLimiter(rate_limit_per_sec)
        self._http = httpx.Client(
            timeout=timeout,
            auth=("api", api_key),
            headers={"Accept": "application/json"},
        )

    @classmethod
    def from_config(cls) -> Self:
        mg = conf.get("mailgun") or {}
        domain = (mg.get("domain") or "").strip()
        if not domain:
            raise RuntimeError("mailgun.domain is not configured")
        region = (mg.get("region") or "eu").lower()
        host = _EU_HOST if region != "us" else _US_HOST
        from_name = (mg.get("from_name") or "").strip()
        from_email = (mg.get("from_email") or "").strip()
        if not from_email:
            raise RuntimeError("mailgun.from_email is not configured")
        from_header = f"{from_name} <{from_email}>" if from_name else from_email

        api_key_path = mg.get("api_key_path")
        if not api_key_path:
            raise RuntimeError("mailgun.api_key_path is not configured")
        key_path = Path(api_key_path)
        if not key_path.is_absolute():
            key_path = PROJECT_DIR / key_path
        if not key_path.exists():
            raise RuntimeError(f"mailgun api key file missing: {key_path}")
        api_key = key_path.read_text(encoding="utf-8").strip()
        if not api_key:
            raise RuntimeError(f"mailgun api key file is empty: {key_path}")

        return cls(
            api_key=api_key,
            domain=domain,
            from_header=from_header,
            host=host,
            rate_limit_per_sec=float(mg.get("rate_limit_per_sec") or 5.0),
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def send_message(  # noqa: PLR0913
        self,
        *,
        to: str,
        recipient_name: str | None,
        subject: str,
        text: str,
        html: str,
        attachments: list[Path] | None = None,
        inlines: list[Path] | None = None,
        bcc: str | None = None,
    ) -> str:
        """POST a multipart message to Mailgun. Returns the Mailgun message-id."""
        to_header = f"{recipient_name} <{to}>" if recipient_name else to
        # httpx 0.28 chokes on `data=[(k, v), ...]` when `files=` is also set —
        # the multipart encoder leaves a tuple inside h11's data buffer and
        # raises a confusing `TypeError: ... expected a bytes-like object, tuple found`.
        # `data` as a dict avoids the bug; we don't need repeated keys here.
        data: dict[str, str] = {
            "from": self.from_header,
            "to": to_header,
            "subject": subject,
            "text": text,
            "html": html,
        }
        if bcc:
            data["bcc"] = bcc

        files: list[tuple[str, tuple[str, bytes, str]]] = []
        for path in attachments or []:
            files.append(("attachment", (path.name, path.read_bytes(), _guess_mime(path))))
        for path in inlines or []:
            # Mailgun uses the bare filename as the Content-ID; templates must
            # reference `cid:<filename>` to match.
            files.append(("inline", (path.name, path.read_bytes(), _guess_mime(path))))

        # One retry on transient HTTP errors.
        last_exc: Exception | None = None
        for attempt in range(2):
            self._rate_limiter.wait()
            try:
                response = self._http.post(self._endpoint, data=data, files=files)
            except httpx.HTTPError as exc:
                last_exc = exc
                logger.warning(f"Mailgun POST attempt {attempt + 1} failed: {exc}")
                time.sleep(2**attempt)
                continue
            if response.status_code // 100 == _HTTP_2XX:
                message_id = (response.json().get("id") or "").strip("<>")
                return message_id
            if response.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                logger.warning(
                    f"Mailgun returned {response.status_code}; retrying once. Body: {response.text[:200]}"
                )
                time.sleep(2)
                continue
            raise MailgunSendError(status_code=response.status_code, body=response.text)

        raise MailgunSendError(status_code=0, body=str(last_exc) if last_exc else "unknown")


_MIME_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}


def _guess_mime(path: Path) -> str:
    return _MIME_BY_SUFFIX.get(path.suffix.lower(), "application/octet-stream")
