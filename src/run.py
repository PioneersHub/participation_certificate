from pathlib import Path

import pandas as pd

from src import conf
from src.generate_certificates import Certificates
from src.preprocess_attendees import ProcessAttendees

if __name__ == "__main__":
    # CUSTOMIZE THIS
    #  example uses `pandas` to load the data from an Excel file.
    #  file to load the data from
    attendees_table = "attendees-pyconde-2024.xlsx"
    # columns to load from the file
    load_columns = {"Ticket Full Name": "full_name",
                    "Ticket First Name": "first_name",
                    "Ticket Email": "email",
                    "Ticket Reference": "ticket_reference",
                    "Ticket": "attended_how",
                    }


    # function to select rows from the DataFrame
    def select_rows(data_frame: pd.DataFrame) -> pd.DataFrame:
        """ Remove rows that are not participants for example for luggage or childcare """
        data_frame = data_frame[~data_frame["Ticket"].str.contains("Social|luggage|Childcare|Keynote|TEST")].reindex()
        data_frame = data_frame[~data_frame["Void Status"].fillna("").str.contains("voided")]
        return data_frame


    # update columns in the DataFrame based on the info
    transformers = {"Ticket": lambda x: "remotely" if "online" in x.lower() else "on site"}
    # noinspection PyTypeChecker
    participants = ProcessAttendees(
        Path(__file__).parents[1] / "_data" / attendees_table,
        load_columns,
        select_rows,
        transformers
    )

    certs = Certificates(participants.attendees,
                         conf.event_short_name,
                         sign_key=Path(__file__).parents[1] / "_signatures" / "keyStore.p12",
                         sign_password=b"cnweie2w873W")
    certs.generate_certificates()
