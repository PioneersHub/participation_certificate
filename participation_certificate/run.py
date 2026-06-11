"""Generate certificates for one cert type at a time.

Usage:
    uv run python participation_certificate/run.py [--type <cert-type>]

The available `--type` values are derived from config (see `build_dispatch`):
`attendee` is always present; `speaker` appears when `speaker.enabled`; and every
config block exposing `load_columns` with `enabled: true` (masterclass,
volunteers, …) is offered automatically — adding a new table-based cert type
needs no code change here.

Attendee output stays at `_certificates/<event>/{upload-to-certificates, records, …}/`.
Other types go under `<event>/<type>/...` so the trees never collide.
"""

import argparse
import functools
import sys
from pathlib import Path

import pandas as pd

from participation_certificate import conf, logger
from participation_certificate.generate_certificates import Certificates, configured_cert_types
from participation_certificate.preprocess_attendees import ProcessAttendees
from participation_certificate.preprocess_speakers import ProcessSpeakers
from participation_certificate.signing import load_signing_key


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
    sign_key, sign_password = load_signing_key()
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


def _masterclass_select_rows(data_frame: pd.DataFrame) -> pd.DataFrame:
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


def _run_table_cert(cert_type: str, select_rows=None) -> None:
    """Shared runner for table-based cert types (masterclass, volunteers, …).

    Reads `conf.<cert_type>.attendees_table` through `load_columns`, applying an
    optional per-type `select_rows`, then generates the certs.
    """
    cfg = conf.get(cert_type)
    if not cfg or not cfg.get("enabled"):
        sys.exit(f"{cert_type}.enabled is false — nothing to do.")
    table = Path(__file__).parents[1] / conf.dirs.data_dir / cfg["attendees_table"]
    participants = ProcessAttendees(table, dict(cfg["load_columns"]), select_rows)
    _generate(cert_type, participants.attendees)


def run_speaker() -> None:
    cfg = conf.get("speaker")
    if not cfg or not cfg.get("enabled"):
        sys.exit("speaker.enabled is false — nothing to do.")
    sessions_path = Path(__file__).parents[1] / conf.dirs.data_dir / cfg["sessions_json"]
    speakers_path = Path(__file__).parents[1] / conf.dirs.data_dir / cfg["speakers_json"]
    participants = ProcessSpeakers(sessions_path, speakers_path)
    _generate("speaker", participants.attendees)


# Per-type select_rows for table-based cert types (None unless a type needs to
# disambiguate its ticket_reference). New table-based types default to None.
_TABLE_SELECT_ROWS = {"masterclass": _masterclass_select_rows}


def build_dispatch() -> dict:
    """Map each configured cert type to its runner.

    The set of types comes from `configured_cert_types()` (the single source of
    truth shared with deliver/reissue). `attendee`/`speaker` have bespoke
    runners; every other (table-based) type — masterclass, volunteer, … — uses
    `_run_table_cert` with an optional per-type `select_rows`.
    """
    runners = {"attendee": run_attendee, "speaker": run_speaker}
    return {
        t: runners.get(t) or functools.partial(_run_table_cert, t, _TABLE_SELECT_ROWS.get(t))
        for t in configured_cert_types()
    }


def main() -> None:
    dispatch = build_dispatch()
    parser = argparse.ArgumentParser(description="Generate one certificate type.")
    parser.add_argument(
        "--type",
        choices=sorted(dispatch),
        default="attendee",
        help="Which certificate type to generate (default: attendee). "
        "Choices are derived from config.",
    )
    args = parser.parse_args()
    logger.info(f"Generating {args.type} certificates for {conf.event_full_name}")
    dispatch[args.type]()


if __name__ == "__main__":
    main()
