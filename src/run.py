from pathlib import Path

import pandas as pd

from src import conf
from src.generate_certificates import Certificates
from src.preprocess_attendees import Attendees

if __name__ == "__main__":

    # CUSTOMIZE THIS
    # file to load the data from
    attendees_table = "attendees-pyconde-2024.xlsx"
    load_columns = {"Ticket Full Name": "full_name",
                    "Ticket First Name": "first_name",
                    "Ticket Email": "email",
                    "Ticket Reference": "ticket_reference",
                    "Ticket": "attended_how"}


    def select_rows(data_frame: pd.DataFrame):
        """ Remove rows that are not participants e.g. for luggage or childcare """
        data_frame = data_frame[~data_frame["Ticket"].str.contains("Social|luggage|Childcare|Keynote|TEST")]
        return data_frame


    # update columns based on the info
    the_transforms = {"Ticket": lambda x: "remotely" if "online" in x.lower() else "on site"}
    participants = Attendees(Path(__file__).parents[1] / "_data" / attendees_table, load_columns, select_rows,
                             the_transforms)

    certs = Certificates(participants.attendees,
                         conf.event_short_name,
                         sign_key=Path(__file__).parents[1] / "_signatures" / "keyStore.p12",
                         sign_password=b"cnweie2w873W")
    certs.generate_certificates()
