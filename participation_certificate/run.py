from pathlib import Path

import pandas as pd

from participation_certificate import conf
from participation_certificate.generate_certificates import Certificates
from participation_certificate.preprocess_attendees import ProcessAttendees

if __name__ == "__main__":
    # CUSTOMIZE THIS
    #  example uses `pandas` to load the data from an Excel file.
    #  file to load the data from
    # attendees_table = "attendees-pyconde-2024.xlsx"
    # # columns to load from the file
    # load_columns = {
    #     "Ticket Full Name": "full_name",
    #     "Ticket First Name": "first_name",
    #     "Ticket Email": "email",
    #     "Ticket Reference": "ticket_reference",
    #     "Ticket": "attended_how",
    # }
    # function to select rows from the DataFrame
    # def select_rows(data_frame: pd.DataFrame) -> pd.DataFrame:
    #     """Remove rows that are not participants for example for luggage or childcare"""
    #     data_frame = data_frame[
    #         ~data_frame["Ticket"].str.contains("Social|luggage|Childcare|Keynote|TEST")
    #     ].reindex()
    #     data_frame = data_frame[~data_frame["Void Status"].fillna("").str.contains("voided")]
    #     return data_frame
    # function to select rows from the DataFrame
    # def select_rows(data_frame: pd.DataFrame) -> pd.DataFrame:
    #     """Remove rows that are not participants for example for luggage or childcare"""
    #     return data_frame
    #
    # # update columns in the DataFrame based on the info
    # # Transform ticket types to attended_how field: must be either "on site" or "remotely"
    # transformers = {"Ticket": lambda x: "remotely" if "online" in x.lower() else "on site"}

    attendees_table = Path(__file__).parents[1] / conf.dirs.data_dir / conf.attendees_table

    load_columns = {
        "first name": "first_name",
        "email": "email",
        "comment": "attended_how",
        # Identity entries for derived columns added in select_rows below.
        # pandas.rename ignores keys that don't exist in the source DataFrame.
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

    # `comment` values are "onsite" / "remote"; Attendee.attended_how must be "on site" / "remotely".
    transformers = {
        "attended_how": lambda x: "remotely" if "remote" in str(x).lower() else "on site"
    }

    # noinspection PyTypeChecker
    participants = ProcessAttendees(
        attendees_table,
        load_columns,
        select_rows,
        transformers,
    )

    attendees = participants.attendees
    if conf.batch_size:
        attendees = attendees[: conf.batch_size]
        print(f"Batch mode: processing first {len(attendees)} of {len(participants.attendees)}")

    certs = Certificates(
        attendees,
        conf.event_short_name,
        sign_key=Path(__file__).parents[1] / "_signatures" / "keyStore.p12",
        sign_password=b"cnweie2w873W",
    )
    certs.generate_certificates()
