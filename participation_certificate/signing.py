"""Shared helper: read the PKCS#12 signing key + password from config.

Both ``run.py`` (full-pipeline generation) and ``reissue.py`` (single-cert
rename) need the same key+password tuple to hand to :class:`Certificates`.
Centralised here so the lookup logic lives in exactly one place.
"""

from pathlib import Path

from participation_certificate import PROJECT_DIR, conf


def load_signing_key() -> tuple[Path | None, bytes | None]:
    """Return ``(sign_key_path, sign_password_bytes)`` or ``(None, None)``.

    Returns ``(None, None)`` when ``conf.signing.sign_key`` is empty — that
    signals "generate unsigned PDFs" and is a legitimate dev-time configuration.
    Raises (via Path / read_bytes) if signing is configured but the keystore or
    password file is missing on disk — fail-fast.
    """
    if not conf.signing.sign_key:
        return None, None
    sign_key = Path(conf.dirs.path_to_signatures) / conf.signing.sign_key
    pw_path = Path(conf.signing.sign_password_path)
    if not pw_path.is_absolute():
        pw_path = PROJECT_DIR / pw_path
    return sign_key, pw_path.read_bytes().strip()
