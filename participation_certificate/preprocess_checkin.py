"""Convert a Pretix check-in list export into the canonical attendees CSV.

The attendee pipeline (:func:`participation_certificate.run.run_attendee`) reads
a CSV with the columns ``first name``, ``last name``, ``organisation``,
``email``, ``comment``. The source of truth for who attended is the **Pretix
check-in list** export (Pretix → Check-in lists → Export → "Check-in list",
XLSX). This module is the standardized, repeatable step that turns that export
into the canonical CSV, so nothing downstream changes.

Behaviour (per the agreed process):

  * **All rows** in the check-in list become attendee records — no filtering on
    the ``Checked in`` column (it is frequently empty in exports) and no
    ticket-type exclusions.
  * Every record is marked **on site**: a physical check-in list implies
    in-person attendance. This is emitted as ``comment = "onsite"``, which
    :func:`run_attendee`'s transformer maps to ``"on site"``. To flag remote
    attendees instead, see the ``comment`` heuristic in ``docs/walkthrough.md``.

Row-level dedup and dropping of records with a missing name/email are *not* done
here — that logic lives once in
:class:`participation_certificate.preprocess_attendees.ProcessAttendees` and runs
when the generated CSV is consumed.

When a ``volunteer`` cert type is configured with ``source_products``, the same
check-in read also emits the filtered volunteer/organizer CSV that
``run.py --type volunteer`` consumes (see :func:`filter_by_product`).

Usage::

    uv run python participation_certificate/preprocess_checkin.py
"""

import re
import sys
from pathlib import Path

import pandas as pd

from participation_certificate import conf, logger

# Pretix "Check-in list" export → canonical attendees CSV. The Pretix schema is
# stable (identical column names across our euroscipy and pyconde exports), so
# the mapping is a constant rather than per-event config. ``comment`` is not a
# source column — it is set to the literal "onsite" for every row.
COLUMN_MAP: dict[str, str] = {
    "Attendee name: Given name": "first name",
    "Attendee name: Family name": "last name",
    "Company": "organisation",
    "Email": "email",
}
# Value written to every ``comment`` cell. run_attendee maps any value NOT
# containing "remote" to "on site"; "onsite" is therefore the on-site marker.
ON_SITE_COMMENT = "onsite"

OUTPUT_COLUMNS = ["first name", "last name", "organisation", "email", "comment"]

# Pretix column carrying the ticket/product name, used to carve out subsets such
# as volunteers/organizers.
PRODUCT_COLUMN = "Product"


def filter_by_product(df: pd.DataFrame, substrings: list[str]) -> pd.DataFrame:
    """Return the check-in rows whose ``Product`` contains any of ``substrings``.

    Case-insensitive substring match. Keeps the **original columns** untouched
    so the subset can be fed to a masterclass-style ``load_columns`` mapping.
    Pure (no I/O); fails fast if the ``Product`` column is absent.
    """
    if PRODUCT_COLUMN not in df.columns:
        raise RuntimeError(
            f"Pretix check-in export is missing the {PRODUCT_COLUMN!r} column "
            f"needed to filter by product. Present columns: {list(df.columns)}"
        )
    pattern = "|".join(re.escape(s) for s in substrings)
    mask = df[PRODUCT_COLUMN].fillna("").str.contains(pattern, case=False, regex=True)
    return df[mask].copy()


def checkin_to_attendees(df: pd.DataFrame) -> pd.DataFrame:
    """Map a raw Pretix check-in DataFrame to the canonical attendees layout.

    Pure (no I/O) so it is unit-testable. Fails fast with a clear error listing
    any required source columns that are absent — no silent fallback.
    """
    missing = [src for src in COLUMN_MAP if src not in df.columns]
    if missing:
        raise RuntimeError(
            "Pretix check-in export is missing required column(s): "
            f"{missing}. Present columns: {list(df.columns)}"
        )

    out = df[list(COLUMN_MAP)].rename(columns=COLUMN_MAP).copy()
    out["comment"] = ON_SITE_COMMENT
    return out[OUTPUT_COLUMNS]


def main() -> None:
    checkin_cfg = conf.get("attendee_checkin") or {}
    checkin_table = checkin_cfg.get("checkin_table")
    if not checkin_table:
        sys.exit(
            "attendee_checkin.checkin_table is not configured — set it to the "
            "Pretix check-in list xlsx filename under dirs.data_dir."
        )
    if not conf.attendees_table:
        sys.exit("attendees_table is not configured — nowhere to write the converted CSV.")

    sheet = checkin_cfg.get("sheet") or "Check-in list"
    source = Path(conf.dirs.data_dir) / checkin_table
    if not source.exists():
        sys.exit(f"Check-in list not found: {source}")

    df = pd.read_excel(source, dtype=str, sheet_name=sheet)
    logger.info(f"Read {len(df)} rows from {source} (sheet {sheet!r}).")

    attendees = checkin_to_attendees(df)

    empty_email = attendees["email"].isna().sum()
    if empty_email:
        logger.warning(
            f"{empty_email} row(s) have an empty Email — they will be dropped "
            "downstream by ProcessAttendees."
        )

    destination = Path(conf.dirs.data_dir) / conf.attendees_table
    attendees.to_csv(destination, index=False)
    logger.info(f"Wrote {len(attendees)} rows to {destination}.")

    _emit_volunteer_subset(df)


def _emit_volunteer_subset(df: pd.DataFrame) -> None:
    """Write the filtered volunteer/organizer CSV when configured.

    Driven by ``conf.volunteer.source_products`` (the Product substrings to
    match) and ``conf.volunteer.attendees_table`` (the destination, shared with
    the volunteer cert type). Skips silently when ``source_products`` is unset —
    the operator is then maintaining that file by hand.
    """
    vol_cfg = conf.get("volunteer") or {}
    products = vol_cfg.get("source_products")
    table = vol_cfg.get("attendees_table")
    if not products:
        return
    if not table:
        sys.exit(
            "volunteer.source_products is set but volunteer.attendees_table is "
            "not — nowhere to write the volunteer subset."
        )

    subset = filter_by_product(df, list(products))
    destination = Path(conf.dirs.data_dir) / table
    subset.to_csv(destination, index=False)
    logger.info(
        f"Wrote {len(subset)} volunteer/organizer rows "
        f"(Product matching {list(products)}) to {destination}."
    )


if __name__ == "__main__":
    main()
