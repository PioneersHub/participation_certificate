"""Re-cut a single signed certificate PDF with a corrected name.

This is the operator's tool for fixing a misspelled / outdated name on a cert
that has already been generated and emailed. It preserves the per-cert
identifiers — `uuid` and `hash` — so every downstream URL stays valid:

  * the S3 download link printed in the email (`…/<uuid>/<uuid>.pdf`)
  * the public validation URL (`https://2026.pycon.de/attendee-certificate/<uuid>/`)
  * the cert's printed serial number ("No. `<hash>`")

What gets regenerated locally
-----------------------------

  * `_certificates/<event>/<type>/upload-to-certificates/<uuid>/<uuid>.pdf`
  * `_certificates/<event>/<type>/records/<uuid>.json`
  * `_certificates/<event>/attendees/website-validate/<uuid>/contents.lr`
    (attendee type only — masterclass/speaker do not publish validation pages)

Operator must then publish: S3 upload, website push, and re-send the email via
`deliver_certificates.py --only <uuid>`. The CLI prints the exact next-step
commands when it finishes.

Usage::

    uv run python participation_certificate/reissue.py \
        --uuid <uuid> --full-name "Jane Smith" \
        [--first-name "Jane"]          # default: first whitespace-split word
        [--type attendee]              # attendee | masterclass | speaker
        [--dry-run]
"""

import argparse
import json
import sys
from pathlib import Path

from participation_certificate import conf, logger
from participation_certificate.generate_certificates import (
    Certificates,
    obfuscate_name,
    type_subdir,
)
from participation_certificate.models.attendee import Attendee
from participation_certificate.signing import load_signing_key

CERT_TYPES = ("attendee", "masterclass", "speaker")
_PDF_MIN_BYTES = 10_000


def _type_root(cert_type: str) -> Path:
    return Path(conf.dirs.path_to_certificates) / conf.event_short_name / type_subdir(cert_type)


def _record_path(cert_type: str, uuid: str) -> Path:
    return _type_root(cert_type) / "records" / f"{uuid}.json"


def _pdf_path(cert_type: str, uuid: str) -> Path:
    return _type_root(cert_type) / "upload-to-certificates" / uuid / f"{uuid}.pdf"


def _validate_path(uuid: str) -> Path:
    return _type_root("attendee") / "website-validate" / uuid / "contents.lr"


def reissue(
    *,
    cert_type: str,
    uuid: str,
    full_name: str,
    first_name: str | None,
    dry_run: bool,
) -> None:
    """Regenerate one cert with a corrected name; UUID + hash stay stable."""
    record_path = _record_path(cert_type, uuid)
    if not record_path.exists():
        sys.exit(f"No record at {record_path}")

    original = json.loads(record_path.read_text(encoding="utf-8"))
    original_uuid = original["uuid"]
    original_hash = original["hash"]
    original_full_name = original["full_name"]
    if original_uuid != uuid:
        # record key on disk vs. uuid inside the JSON disagree — refuse rather than guess
        sys.exit(f"Record file uuid {original_uuid!r} does not match path uuid {uuid!r}")

    new_first = (first_name or full_name.split(maxsplit=1)[0]).strip()

    logger.info(
        f"Reissue [{cert_type}] uuid={original_uuid}: "
        f"name {original_full_name!r} -> {full_name!r} (hash {original_hash} stable)"
    )

    if dry_run:
        logger.info("[dry-run] would regenerate:")
        logger.info(f"  PDF      {_pdf_path(cert_type, original_uuid)}")
        logger.info(f"  record   {record_path}")
        if cert_type == "attendee":
            logger.info(f"  validate {_validate_path(original_uuid)}")
        logger.info("[dry-run] no files written.")
        return

    # Build the updated dict. Drop uuid/hash so model_post_init doesn't see stale
    # values; clear mail_status so a follow-up `deliver --only` will resend.
    # Preserve mail_message_id + mail_sent_at as a historical audit trail.
    updated = dict(original)
    updated["full_name"] = full_name
    updated["first_name"] = new_first
    updated.pop("uuid", None)
    updated.pop("hash", None)
    updated["mail_status"] = None
    updated["mail_failed_at"] = None
    updated["mail_last_error"] = None

    attendee = Attendee(**updated)
    # model_post_init derived a NEW uuid + hash from the new name — restore.
    attendee.uuid = original_uuid
    attendee.hash = original_hash

    sign_key, sign_password = load_signing_key()
    certs = Certificates(
        [attendee],
        conf.event_short_name,
        sign_key=sign_key,
        sign_password=sign_password,
        cert_type=cert_type,
    )
    certs.generate_certificate(attendee)

    # Self-checks — use `raise` (not `assert`) so they survive `python -O`,
    # since these guard against real pipeline bugs, not mypy type-narrowing.
    new_record = json.loads(record_path.read_text(encoding="utf-8"))
    if new_record["uuid"] != original_uuid:
        raise RuntimeError(
            f"uuid drifted after generate_certificate: {original_uuid!r} → {new_record['uuid']!r}"
        )
    if new_record["hash"] != original_hash:
        raise RuntimeError(
            f"hash drifted after generate_certificate: {original_hash!r} → {new_record['hash']!r}"
        )
    if new_record["full_name"] != full_name:
        raise RuntimeError(
            f"full_name not updated on record: expected {full_name!r}, got {new_record['full_name']!r}"
        )
    pdf = _pdf_path(cert_type, original_uuid)
    if not pdf.exists() or pdf.stat().st_size <= _PDF_MIN_BYTES:
        raise RuntimeError(f"PDF missing or implausibly small at {pdf}")
    if cert_type == "attendee":
        validate_text = _validate_path(original_uuid).read_text(encoding="utf-8")
        expected_obfuscated = obfuscate_name(full_name)
        if expected_obfuscated not in validate_text:
            raise RuntimeError(
                f"validation page does not contain obfuscated new name {expected_obfuscated!r}"
            )

    _print_next_steps(cert_type, original_uuid)


def _print_next_steps(cert_type: str, uuid: str) -> None:
    pdf = _pdf_path(cert_type, uuid)
    # `certificates_s3_uri` is the `s3://bucket/prefix` write target (optional).
    # `certificates_url` is the public-read HTTPS prefix used in emails.
    s3_uri_prefix = (conf.get("certificates_s3_uri") or "").rstrip("/")
    logger.info("")
    logger.info("Local files updated:")
    logger.info(f"  PDF      {pdf}")
    logger.info(f"  record   {_record_path(cert_type, uuid)}")
    if cert_type == "attendee":
        logger.info(f"  validate {_validate_path(uuid)}")
    logger.info("")
    logger.info("Operator next steps:")
    if s3_uri_prefix:
        logger.info(f"  1. aws s3 cp {pdf} {s3_uri_prefix}/{uuid}/{uuid}.pdf")
    else:
        logger.info(
            f"  1. push {pdf} to the configured S3 location "
            f"(set `certificates_s3_uri` in config_local.yaml to fill this in)"
        )
    if cert_type == "attendee":
        logger.info(
            f"  2. cp {_validate_path(uuid)} "
            f"<WEBSITE>/content/attendee-certificate/{uuid}/contents.lr"
        )
        logger.info(
            f"     (cd <WEBSITE> && git add -f content/attendee-certificate/{uuid}/contents.lr"
            f' && git commit -m "reissue {uuid}" && git push)'
        )
        next_idx = 3
    else:
        next_idx = 2
    logger.info(
        f"  {next_idx}. uv run python participation_certificate/deliver_certificates.py "
        f"--type {cert_type} --only {uuid}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reissue a single signed certificate with a corrected name.",
    )
    parser.add_argument("--uuid", required=True, help="UUID of the cert to reissue.")
    parser.add_argument(
        "--full-name",
        required=True,
        help="The corrected full name to print on the certificate.",
    )
    parser.add_argument(
        "--first-name",
        default=None,
        help="Override the first name used in email greetings. "
        "Defaults to the first whitespace-split word of --full-name.",
    )
    parser.add_argument(
        "--type",
        choices=CERT_TYPES,
        default="attendee",
        help="Cert type (default: attendee).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the name diff and planned file writes without touching disk.",
    )
    args = parser.parse_args()

    if not args.full_name.strip():
        parser.error("--full-name must not be empty")

    reissue(
        cert_type=args.type,
        uuid=args.uuid,
        full_name=args.full_name.strip(),
        first_name=args.first_name,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
