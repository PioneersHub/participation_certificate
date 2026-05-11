"""Sync the local Lektor staging trees to the external Lektor site directories.

Each cert type has its own staging tree under `_certificates/<event>/[<type>/]`:
    records/<uuid>.json
    website-validate/<uuid>/contents.lr
    website-share/<share_hash>/{contents.lr, <share_hash>.png}

For the attendee type, that staging lives at the event root (back-compat). For
masterclass and speaker, it lives under the per-type subdir.

Per-type Lektor destinations are read from `conf.<type>.static_pages_website` and
`conf.<type>.share_pages_website`. The attendee type uses the top-level
`static_pages_website` / `share_pages_website`.
"""

import json
import shutil
from pathlib import Path

from participation_certificate import conf, logger
from participation_certificate.generate_certificates import (
    obfuscate_name,
    type_subdir,
    write_share_page,
    write_validation_page,
)
from participation_certificate.models.attendee import Attendee

EVENT_ROOT = Path(__file__).parents[1] / conf.dirs.path_to_certificates / conf.event_short_name


def _type_root(cert_type: str) -> Path:
    return EVENT_ROOT / type_subdir(cert_type)


def _type_destinations(cert_type: str) -> tuple[Path, Path | None]:
    """Return (validation_dest, share_dest_or_None) for the cert type."""
    if cert_type == "attendee":
        validate = Path(conf.static_pages_website)
        share_raw = conf.get("share_pages_website") or ""
        share = Path(share_raw) if share_raw else None
        return validate, share
    cfg = conf.get(cert_type) or {}
    validate = Path(cfg.get("static_pages_website") or "")
    share_raw = cfg.get("share_pages_website") or ""
    share = Path(share_raw) if share_raw else None
    if not validate.parts:
        validate = Path(conf.static_pages_website)
    return validate, share


def sync_type(cert_type: str, replace: bool = False) -> None:
    root = _type_root(cert_type)
    records_dir = root / "records"
    if not records_dir.exists():
        logger.info(f"No records dir at {records_dir} — skipping {cert_type}.")
        return

    validate_dest, share_dest = _type_destinations(cert_type)
    local_validate = root / "website-validate"
    local_share = root / "website-share"

    for record in sorted(records_dir.glob("*.json")):
        attendee = Attendee(**json.loads(record.read_text()))
        # uuid / share_hash are populated by model_post_init; the model declares
        # them Optional so assert here to narrow the type for mypy + downstream.
        assert attendee.uuid and attendee.share_hash
        logger.info(
            f"[{cert_type}] {attendee.full_name} -> {obfuscate_name(attendee.full_name)} "
            f"uuid={attendee.uuid} share={attendee.share_hash}"
        )

        # Validation page (UUID-keyed).
        src_validate = local_validate / attendee.uuid / "contents.lr"
        if src_validate.exists():
            dst_validate = validate_dest / attendee.uuid / "contents.lr"
            if not dst_validate.exists() or replace:
                dst_validate.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_validate, dst_validate)
        else:
            # Regenerate from the record (fallback if local staging was wiped).
            target = validate_dest / attendee.uuid
            if not (target / "contents.lr").exists() or replace:
                target.mkdir(parents=True, exist_ok=True)
                write_validation_page(attendee, target, cert_type)

        # Share page + PNG (share_hash-keyed).
        if share_dest is None:
            continue
        src_share_dir = local_share / attendee.share_hash
        if not src_share_dir.exists():
            logger.warning(f"Share dir missing for {attendee.share_hash}: {src_share_dir}")
            continue
        dst_share_dir = share_dest / attendee.share_hash
        if (dst_share_dir / "contents.lr").exists() and not replace:
            continue
        dst_share_dir.mkdir(parents=True, exist_ok=True)
        for src in src_share_dir.iterdir():
            shutil.copy2(src, dst_share_dir / src.name)
        # Regenerate share contents.lr from the record so per-type texts always reflect
        # the current config (cheap; replaces what was just copied).
        if not (dst_share_dir / "contents.lr").exists() or replace:
            write_share_page(attendee, dst_share_dir, cert_type)


def create_static_pages(replace: bool = False) -> None:
    """Sync attendee + any enabled non-attendee cert types."""
    sync_type("attendee", replace)
    for cert_type in ("masterclass", "speaker"):
        if (conf.get(cert_type) or {}).get("enabled"):
            sync_type(cert_type, replace)


if __name__ == "__main__":
    create_static_pages()
