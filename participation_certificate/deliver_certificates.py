"""Deliver certificate PDFs via Mailgun with branded HTML emails.

Multi-step flow (intentional, mirroring conference_ticket_distribute/send_emails.py):

  1. `--dry-run` writes per-recipient `.html`/`.txt` previews under
     `_certificates/<event>/<type>/email-preview/` plus a `send-preview-<UTC>.xlsx`
     index. The operator opens the HTML files in a browser to sanity-check
     branding, copy and links before sending anything.
  2. `--override-recipient <email>` performs a real send through Mailgun but
     redirects every message to one test inbox. Real cert content, real PDF,
     real branding — only the To: address flips. **No state is persisted**, so
     a subsequent real run still picks the records up via idempotent retry.
  3. A real run (no `--dry-run`, no `--override-recipient`) sends each email
     via Mailgun, attaches the signed PDF, inlines the brand logo as a CID
     image, and persists `mail_status` / `mail_message_id` / `mail_sent_at`
     back into the `records/<uuid>.json` file. Re-runs are idempotent —
     records with `mail_status == "sent"` are skipped unless `--only` is supplied.

CLI:

    uv run python participation_certificate/deliver_certificates.py \\
        --type {attendee|masterclass|speaker} \\
        [--dry-run | --override-recipient <email>] \\
        [--only <uuid> [--only <uuid>...]] [--limit N] [--bcc <addr>]
"""

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from openpyxl import Workbook

from participation_certificate import conf, logger
from participation_certificate.email_renderer import RenderedEmail, render_email
from participation_certificate.generate_certificates import type_subdir
from participation_certificate.mailgun import MailgunClient, MailgunSendError
from participation_certificate.models.attendee import Attendee

CERT_TYPES = ("attendee", "masterclass", "speaker")


@dataclass
class Job:
    record_path: Path
    attendee: Attendee
    pdf_path: Path
    rendered: RenderedEmail


# ---------------------------------------------------------------------------
# Job loading
# ---------------------------------------------------------------------------


def _type_root(cert_type: str) -> Path:
    return Path(conf.dirs.path_to_certificates) / conf.event_short_name / type_subdir(cert_type)


def _records_dir(cert_type: str) -> Path:
    return _type_root(cert_type) / "records"


def _pdf_path(cert_type: str, attendee: Attendee) -> Path:
    assert attendee.uuid
    return _type_root(cert_type) / "upload-to-certificates" / attendee.uuid / f"{attendee.uuid}.pdf"


def _preview_dir(cert_type: str) -> Path:
    return _type_root(cert_type) / "email-preview"


def load_jobs(
    cert_type: str,
    *,
    only: set[str] | None = None,
    limit: int | None = None,
) -> tuple[list[Job], list[str]]:
    """Walk records/*.json for `cert_type` and assemble Job entries.

    Returns (jobs, skipped_messages). `skipped_messages` captures records that
    were filtered out (already sent, missing PDF, --only mismatch).
    """
    records_dir = _records_dir(cert_type)
    if not records_dir.exists():
        raise FileNotFoundError(f"No records dir at {records_dir}")

    jobs: list[Job] = []
    skipped: list[str] = []
    for record_path in sorted(records_dir.glob("*.json")):
        attendee = Attendee(**json.loads(record_path.read_text(encoding="utf-8")))
        if only is not None and attendee.uuid not in only:
            continue
        if only is None and attendee.mail_status == "sent":
            skipped.append(f"{attendee.uuid} already sent ({attendee.mail_sent_at})")
            continue
        pdf = _pdf_path(cert_type, attendee)
        if not pdf.exists():
            skipped.append(f"{attendee.uuid} skipped: PDF missing at {pdf}")
            continue
        rendered = render_email(cert_type, attendee)
        jobs.append(
            Job(record_path=record_path, attendee=attendee, pdf_path=pdf, rendered=rendered)
        )
        if limit and len(jobs) >= limit:
            break
    return jobs, skipped


# ---------------------------------------------------------------------------
# Preview output
# ---------------------------------------------------------------------------


def write_previews(
    cert_type: str,
    jobs: list[Job],
    skipped: list[str],
    *,
    override_recipient: str | None = None,
) -> Path:
    """Write per-recipient HTML/TXT previews + a send-preview-<UTC>.xlsx index.

    The xlsx has a `delivered_to` column: for normal runs it equals the
    attendee's real email; for smoke runs (``override_recipient`` set) it shows
    the override address so the operator can audit which rows were redirected.

    Returns the path to the xlsx file.
    """
    preview_dir = _preview_dir(cert_type)
    preview_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    xlsx_path = preview_dir / f"send-preview-{stamp}.xlsx"

    wb = Workbook()
    sheet = wb.active
    sheet.title = "preview"
    sheet.append(
        [
            "uuid",
            "email",
            "delivered_to",
            "name",
            "subject",
            "status",
            "mail_message_id",
            "preview_html",
        ]
    )

    for job in jobs:
        a = job.attendee
        html_path = preview_dir / f"{a.uuid}.html"
        txt_path = preview_dir / f"{a.uuid}.txt"
        html_path.write_text(job.rendered.html, encoding="utf-8")
        txt_path.write_text(job.rendered.text, encoding="utf-8")
        sheet.append(
            [
                a.uuid,
                a.email,
                override_recipient or a.email,
                a.full_name,
                job.rendered.subject,
                a.mail_status or "pending",
                a.mail_message_id or "",
                str(html_path),
            ]
        )

    if skipped:
        sheet2 = wb.create_sheet("skipped")
        sheet2.append(["reason"])
        for msg in skipped:
            sheet2.append([msg])

    wb.save(xlsx_path)
    return xlsx_path


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------


def _persist_status(job: Job, **updates: str | None) -> None:
    """Merge `updates` into the on-disk record JSON and the attendee model.

    Re-loads the existing JSON so any other fields persisted earlier (e.g. by a
    previous failed run) survive untouched.
    """
    data = json.loads(job.record_path.read_text(encoding="utf-8"))
    for key, value in updates.items():
        data[key] = value
        setattr(job.attendee, key, value)
    job.record_path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")


def _logo_path() -> Path:
    branding = conf.get("branding") or {}
    raw = branding.get("logo_path") or "assets/email/pyconde-pydata-2026-logo.png"
    p = Path(raw)
    if not p.is_absolute():
        p = Path(__file__).parents[1] / p
    if not p.exists():
        raise FileNotFoundError(
            f"Branding logo not found at {p}. Copy the chosen logo into place "
            "(see assets/email/README.md)."
        )
    return p


def send_jobs(
    jobs: list[Job],
    *,
    cert_type: str,
    bcc: str | None,
    override_recipient: str | None = None,
) -> tuple[int, int]:
    """Send each job via Mailgun. Returns (sent, failed).

    When ``override_recipient`` is set, every email is redirected to that single
    address regardless of the attendee's real email — useful for a smoke test
    that exercises the real Mailgun call with real cert content. **No state is
    persisted to `records/<uuid>.json` in smoke mode**, so the subsequent real
    send still picks the record up via idempotent retry.
    """
    if not jobs:
        return 0, 0

    smoke = override_recipient is not None
    logo = _logo_path()
    sent = failed = 0
    with MailgunClient.from_config() as client:
        for i, job in enumerate(jobs, 1):
            a = job.attendee
            if smoke:
                assert override_recipient is not None  # narrowed by `smoke` flag
                logger.info(
                    f"[{cert_type}] [smoke] {i}/{len(jobs)} redirect {a.email} -> "
                    f"{override_recipient} (uuid={a.uuid})"
                )
                to_addr = override_recipient
                to_name = "Smoke test"
            else:
                logger.info(f"[{cert_type}] sending {i}/{len(jobs)} to {a.email} (uuid={a.uuid})")
                to_addr = a.email
                to_name = a.full_name
            try:
                message_id = client.send_message(
                    to=to_addr,
                    recipient_name=to_name,
                    subject=job.rendered.subject,
                    text=job.rendered.text,
                    html=job.rendered.html,
                    attachments=[job.pdf_path],
                    inlines=[logo],
                    bcc=bcc,
                )
            except MailgunSendError as exc:
                logger.error(f"[{cert_type}] {a.uuid} send failed: {exc}")
                if not smoke:
                    _persist_status(
                        job,
                        mail_status="failed",
                        mail_failed_at=datetime.now(UTC).isoformat(),
                        mail_last_error=str(exc),
                    )
                failed += 1
                continue
            if not smoke:
                _persist_status(
                    job,
                    mail_status="sent",
                    mail_message_id=message_id,
                    mail_sent_at=datetime.now(UTC).isoformat(),
                    mail_last_error=None,
                )
            sent += 1
    return sent, failed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Send branded certificate emails via Mailgun.")
    parser.add_argument(
        "--type",
        choices=CERT_TYPES,
        default="attendee",
        help="Cert type to deliver (default: attendee).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render previews + xlsx index only; do not send.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Restrict to one or more UUIDs (repeatable). Overrides the skip-already-sent filter.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N records.",
    )
    parser.add_argument(
        "--bcc",
        default=None,
        help="BCC every sent message to this address (defaults to conf.email.bcc).",
    )
    parser.add_argument(
        "--override-recipient",
        default=None,
        help=(
            "Smoke test: send every email (real content, real PDF) to this address "
            "instead of the attendee's. records/<uuid>.json is NOT modified, so a "
            "later real send is unaffected. Combine with --limit N to keep the batch small."
        ),
    )
    args = parser.parse_args()

    if args.override_recipient and "@" not in args.override_recipient:
        parser.error(
            f"--override-recipient does not look like an email: {args.override_recipient!r}"
        )
    if args.override_recipient and args.dry_run:
        parser.error("--override-recipient + --dry-run is meaningless (nothing is sent); pick one.")

    only = set(args.only) or None
    bcc = args.bcc or ((conf.get("email") or {}).get("bcc") or None)

    logger.info(f"[{args.type}] loading records from {_records_dir(args.type)}")
    jobs, skipped = load_jobs(args.type, only=only, limit=args.limit)
    logger.info(f"[{args.type}] {len(jobs)} job(s) ready; {len(skipped)} skipped")

    xlsx = write_previews(args.type, jobs, skipped, override_recipient=args.override_recipient)
    logger.info(f"[{args.type}] preview index: {xlsx}")

    if args.dry_run:
        logger.info(f"[{args.type}] dry-run — not sending. Open the HTML previews to review.")
        return

    sent, failed = send_jobs(
        jobs,
        cert_type=args.type,
        bcc=bcc,
        override_recipient=args.override_recipient,
    )
    mode = f"smoke→{args.override_recipient}" if args.override_recipient else "live"
    logger.info(
        f"[{args.type}] done ({mode}) — seen={len(jobs) + len(skipped)} sent={sent} "
        f"failed={failed} skipped={len(skipped)} preview={xlsx}"
    )


if __name__ == "__main__":
    main()
