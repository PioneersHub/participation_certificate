import pandas as pd
import pytest

from participation_certificate.preprocess_checkin import (
    ON_SITE_COMMENT,
    OUTPUT_COLUMNS,
    checkin_to_attendees,
    filter_by_product,
)


def _raw_checkin() -> pd.DataFrame:
    """A minimal Pretix check-in export: a normal row, a speaker row, and a
    row with an empty email (kept here, dropped downstream)."""
    return pd.DataFrame(
        {
            "Order code": ["Q37NT", "3ZGAD", "TPVVG"],
            "Attendee name": ["Ada Böhm", "Adam Staniszewski", "No Email"],
            "Attendee name: Given name": ["Ada", "Adam", "No"],
            "Attendee name: Family name": ["Böhm", "Staniszewski", "Email"],
            "Product": ["Speaker Ticket (Conference)", "Conference", "Conference"],
            "Email": ["ada@example.cz", "adam@example.com", None],
            "Company": ["IT4I", None, "Acme"],
        }
    )


def test_maps_to_canonical_columns():
    out = checkin_to_attendees(_raw_checkin())
    assert list(out.columns) == OUTPUT_COLUMNS
    assert out.loc[0, "first name"] == "Ada"
    assert out.loc[0, "last name"] == "Böhm"
    assert out.loc[0, "organisation"] == "IT4I"
    assert out.loc[0, "email"] == "ada@example.cz"


def test_every_row_marked_on_site():
    out = checkin_to_attendees(_raw_checkin())
    assert (out["comment"] == ON_SITE_COMMENT).all()


def test_all_rows_carried_through_no_exclusions():
    raw = _raw_checkin()
    out = checkin_to_attendees(raw)
    # Speaker-ticket row and the empty-email row are both retained here.
    assert len(out) == len(raw)


def test_missing_required_column_fails_fast():
    raw = _raw_checkin().drop(columns=["Email"])
    with pytest.raises(RuntimeError, match="missing required column"):
        checkin_to_attendees(raw)


def _raw_with_products() -> pd.DataFrame:
    """Check-in rows spanning organizer/volunteer and unrelated products."""
    return pd.DataFrame(
        {
            "Order code": ["A1", "B2", "C3", "D4"],
            "Attendee name": ["Org One", "Vol Two", "Attendee Three", "Speaker Four"],
            "Email": ["o@x.org", "v@x.org", "a@x.org", "s@x.org"],
            "Product": ["Organizers", "Volunteers", "Conference (Wed+Thu)", "Speaker Ticket"],
        }
    )


def test_filter_by_product_matches_case_insensitive_substring():
    out = filter_by_product(_raw_with_products(), ["organizer", "volunteer"])
    assert list(out["Order code"]) == ["A1", "B2"]  # only Organizers + Volunteers
    # Raw columns are preserved untouched (so masterclass-style load_columns maps).
    assert list(out.columns) == ["Order code", "Attendee name", "Email", "Product"]


def test_filter_by_product_no_match_returns_empty():
    out = filter_by_product(_raw_with_products(), ["sponsor"])
    assert len(out) == 0


def test_filter_by_product_missing_product_column_fails_fast():
    raw = _raw_with_products().drop(columns=["Product"])
    with pytest.raises(RuntimeError, match="Product"):
        filter_by_product(raw, ["volunteer"])
