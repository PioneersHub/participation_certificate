import argparse
import json
import shutil
from pathlib import Path

from pydantic import BaseModel
from pytanis.helpdesk import Mail, Recipient

from participation_certificate import conf, logger
from participation_certificate.email_providers import get_email_provider
from participation_certificate.generate_certificates import type_subdir
from participation_certificate.models.attendee import Attendee


def _type_conf(cert_type: str):
    return conf if cert_type == "attendee" else (conf.get(cert_type) or {})


def _share_url(attendee: Attendee, cert_type: str) -> str:
    """Public share URL — share_hash-keyed, never UUID-keyed."""
    tc = _type_conf(cert_type)
    base = (tc.get("share_url") if cert_type != "attendee" else None) or conf.get("share_url") or ""
    return f"{base.rstrip('/')}/{attendee.share_hash}/" if base else ""


def _email_section(cert_type: str) -> dict:
    """Per-type email section. Falls back to the top-level `email` block."""
    tc = _type_conf(cert_type)
    if cert_type != "attendee":
        per_type = tc.get("email") if tc else None
        if per_type:
            return per_type
    return conf.email


def message(attendee: Attendee, cert_type: str = "attendee") -> str:
    """Render the delivery email from the cert type's `email.body_template`."""
    email_conf = _email_section(cert_type)
    template = email_conf.get("body_template") or ""
    share_line_tpl = email_conf.get("share_line") or ""
    share_url = _share_url(attendee, cert_type)
    share_block = (
        f"\n{share_line_tpl.format(share_url=share_url, event_full_name=conf.event_full_name)}\n"
        if share_url and share_line_tpl
        else ""
    )
    return template.format(
        first_name=attendee.first_name,
        event_full_name=conf.event_full_name,
        certificates_url=conf.certificates_url,
        uuid=attendee.uuid,
        share_block=share_block,
        # Type-specific placeholders — None for the type that doesn't carry them.
        masterclass=attendee.masterclass or "",
        talk_title=attendee.talk_title or "",
    )


class Job(BaseModel):
    attendee: Attendee
    file: Path
    cert_type: str = "attendee"


def collect_certificates(cert_type: str = "attendee") -> list[Job]:
    event_root = conf.dirs.path_to_certificates / conf.event_short_name
    type_root = event_root / type_subdir(cert_type)
    records_dir = type_root / "records"
    pdf_root = type_root / "upload-to-certificates"
    upload_mirror = (
        conf.dirs.path_to_certificates / f"{conf.event_short_name}-{type_subdir(cert_type)}_upload"
    )
    upload_mirror.mkdir(exist_ok=True, parents=True)

    jobs: list[Job] = []
    for record in sorted(records_dir.glob("*.json")):
        attendee = Attendee(**json.loads(record.read_text()))
        pdf = pdf_root / attendee.uuid / f"{attendee.uuid}.pdf"
        if not pdf.exists():
            logger.warning(f"[{cert_type}] PDF missing for {attendee.uuid}: {pdf}")
            continue
        logger.info(f"[{cert_type}] Processing {attendee.uuid}")
        dst = upload_mirror / f"{attendee.uuid}.pdf"
        if not dst.exists():
            shutil.copy(pdf, dst)
        jobs.append(Job(attendee=attendee, file=pdf, cert_type=cert_type))
    return jobs


def send_certificates(jobs: list[Job], dry_run: bool = False) -> None:
    provider_name = conf.email.provider
    provider_config = conf.email.get(provider_name, {})
    try:
        email_provider = get_email_provider(provider_name, provider_config)
    except Exception as e:
        logger.error(f"Failed to initialize email provider: {e}")
        return

    logger.info(f"Using {provider_name} email provider to send {len(jobs)} certificates")

    for i, job in enumerate(jobs, 1):
        recipients = [
            Recipient(
                name=job.attendee.full_name,
                email=job.attendee.email,
                address_as=job.attendee.first_name,
            )
        ]
        mail = Mail(
            subject=f"Certificate of Attendance: {conf.event_full_name}",
            text=message(attendee=job.attendee, cert_type=job.cert_type),
            recipients=recipients,
            team_id=None,
            agent_id=None,
        )
        if provider_name == "helpdesk" and conf.email.helpdesk.get("team_id"):
            mail.team_id = conf.email.helpdesk.team_id

        logger.info(f"Sending {i}/{len(jobs)} ({job.cert_type}) to {job.attendee.email}")
        responses, errors = email_provider.send(mail, dry_run=dry_run)
        if errors:
            logger.error(f"Error sending mail to {job.attendee.email}: {errors}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Deliver certificates for one type.")
    parser.add_argument(
        "--type",
        choices=("attendee", "masterclass", "speaker"),
        default="attendee",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    jobs = collect_certificates(args.type)
    send_certificates(jobs, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
