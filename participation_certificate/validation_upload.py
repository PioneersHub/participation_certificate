"""Sync the local Lektor validation tree to the external PyCon DE website checkout.

Only attendee certs are published on the website — masterclass and speaker
certs are delivered solely by email.

Layout (attendees only):

    _certificates/<event>/attendees/
        records/<uuid>.json                 — full Attendee dump (read-back for sync)
        website-validate/<uuid>/contents.lr — Lektor page → website checkout

The Lektor destination comes from `conf.static_pages_website`.
"""

import json
import shutil
from pathlib import Path

from participation_certificate import conf, logger
from participation_certificate.generate_certificates import (
    obfuscate_name,
    type_subdir,
    write_validation_page,
)
from participation_certificate.models.attendee import Attendee

EVENT_ROOT = Path(__file__).parents[1] / conf.dirs.path_to_certificates / conf.event_short_name


def sync_attendee_validation(replace: bool = False) -> None:
    """Copy every attendee `website-validate/<uuid>/contents.lr` to the PyCon checkout.

    If a local file is missing for a record, regenerate it from the record JSON
    (cheap; covers the "I wiped the staging dir" case).
    """
    root = EVENT_ROOT / type_subdir("attendee")
    records_dir = root / "records"
    if not records_dir.exists():
        logger.info(f"No records dir at {records_dir} — nothing to sync.")
        return

    validate_dest = Path(conf.static_pages_website)
    local_validate = root / "website-validate"

    for record in sorted(records_dir.glob("*.json")):
        attendee = Attendee(**json.loads(record.read_text()))
        assert attendee.uuid
        logger.info(
            f"[attendee] {attendee.full_name} -> {obfuscate_name(attendee.full_name)} "
            f"uuid={attendee.uuid}"
        )

        src_validate = local_validate / attendee.uuid / "contents.lr"
        dst_validate = validate_dest / attendee.uuid / "contents.lr"
        if src_validate.exists():
            if not dst_validate.exists() or replace:
                dst_validate.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_validate, dst_validate)
        else:
            target = validate_dest / attendee.uuid
            if not (target / "contents.lr").exists() or replace:
                target.mkdir(parents=True, exist_ok=True)
                write_validation_page(attendee, target, "attendee")


if __name__ == "__main__":
    sync_attendee_validation()
