"""Generate certificates for one cert type at a time.

Usage:
    uv run python participation_certificate/run.py [--type attendee|masterclass|speaker]

Attendee output stays at `_certificates/<event>/{upload-to-certificates, records, …}/`.
Masterclass and speaker outputs go under `<event>/<type>/...` so the three trees never
collide. Each type is gated on `conf.<type>.enabled` (attendee is implicit, always on).
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from participation_certificate import conf, logger
from participation_certificate.generate_certificates import Certificates
from participation_certificate.preprocess_attendees import ProcessAttendees
from participation_certificate.preprocess_speakers import ProcessSpeakers


def _load_signing() -> tuple[Path | None, bytes | None]:
    if not conf.signing.sign_key:
        return None, None
    sign_key = Path(conf.dirs.path_to_signatures) / conf.signing.sign_key
    pw_path = Path(__file__).parents[1] / conf.signing.sign_password_path
    sign_password = pw_path.read_bytes().strip()
    return sign_key, sign_password


def _batch_size_for(cert_type: str) -> int:
    """Per-type batch_size override; falls back to the top-level batch_size.

    A value of ``0`` (at either level) means "no limit, process everything".
    Use ``is not None`` so an explicit ``0`` at the per-type level overrides a
    non-zero top-level value, rather than falling through.
    """
    if cert_type != "attendee":
        per_type = (conf.get(cert_type) or {}).get("batch_size")
        if per_type is not None:
            return per_type
    return conf.batch_size or 0


def _apply_batch(attendees, cert_type: str):
    n = _batch_size_for(cert_type)
    if n:
        clipped = attendees[:n]
        print(f"Batch mode ({cert_type}): processing first {len(clipped)} of {len(attendees)}")
        return clipped
    return attendees


def _generate(cert_type: str, attendees) -> None:
    attendees = _apply_batch(attendees, cert_type)
    sign_key, sign_password = _load_signing()
    certs = Certificates(
        attendees,
        conf.event_short_name,
        sign_key=sign_key,
        sign_password=sign_password,
        cert_type=cert_type,
    )
    certs.generate_certificates()


def run_attendee() -> None:
    attendees_table = Path(__file__).parents[1] / conf.dirs.data_dir / conf.attendees_table
    load_columns = {
        "first name": "first_name",
        "email": "email",
        "comment": "attended_how",
        # Identity entries for derived columns added in select_rows below.
        "full_name": "full_name",
        "ticket_reference": "ticket_reference",
    }

    def select_rows(data_frame: pd.DataFrame) -> pd.DataFrame:
        """Derive full_name and ticket_reference; the source CSV has neither."""
        data_frame["full_name"] = (
            data_frame["first_name"].str.strip() + " " + data_frame["last name"].str.strip()
        )
        data_frame["ticket_reference"] = data_frame["email"]
        return data_frame

    transformers = {
        "attended_how": lambda x: "remotely" if "remote" in str(x).lower() else "on site"
    }
    participants = ProcessAttendees(attendees_table, load_columns, select_rows, transformers)
    _generate("attendee", participants.attendees)


def run_masterclass() -> None:
    cfg = conf.get("masterclass")
    if not cfg or not cfg.get("enabled"):
        sys.exit("masterclass.enabled is false — nothing to do.")
    table = Path(__file__).parents[1] / conf.dirs.data_dir / cfg["attendees_table"]
    load_columns = dict(cfg["load_columns"])

    def select_rows(data_frame: pd.DataFrame) -> pd.DataFrame:
        """Compose ticket_reference from Order code + Product.

        Pretix Order codes are per-order, not per-enrollment, so one order
        containing two half-day masterclasses produces two rows that share an
        Order code. Mixing the Product into the ticket_reference keeps the two
        enrollments distinct in the UUID hash + dedupe key.
        """
        data_frame["ticket_reference"] = (
            data_frame["ticket_reference"].astype(str).str.strip()
            + " "
            + data_frame["masterclass"].astype(str).str.strip()
        )
        return data_frame

    participants = ProcessAttendees(table, load_columns, select_rows)
    _generate("masterclass", participants.attendees)


def run_speaker() -> None:
    cfg = conf.get("speaker")
    if not cfg or not cfg.get("enabled"):
        sys.exit("speaker.enabled is false — nothing to do.")
    sessions_path = Path(__file__).parents[1] / conf.dirs.data_dir / cfg["sessions_json"]
    speakers_path = Path(__file__).parents[1] / conf.dirs.data_dir / cfg["speakers_json"]
    participants = ProcessSpeakers(sessions_path, speakers_path)
    _generate("speaker", participants.attendees)


DISPATCH = {
    "attendee": run_attendee,
    "masterclass": run_masterclass,
    "speaker": run_speaker,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate one certificate type.")
    parser.add_argument(
        "--type",
        choices=list(DISPATCH),
        default="attendee",
        help="Which certificate type to generate (default: attendee).",
    )
    args = parser.parse_args()
    logger.info(f"Generating {args.type} certificates for {conf.event_full_name}")
    DISPATCH[args.type]()


if __name__ == "__main__":
    main()
