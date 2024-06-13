import base64
import hashlib
from collections.abc import Callable
from pathlib import Path

import pandas as pd
from pydantic import UUID4, BaseModel, EmailStr

from src import logger


class Attendee(BaseModel):
    full_name: str
    first_name: str
    email: EmailStr
    ticket_reference: str
    attended_how: str
    hash: str | None = None
    uuid: str | None = None

    def model_post_init(self, ctx):  # noqa: ARG002
        # short hash to identify the attendee
        hash_this = ''.join([x.upper() for x in self.full_name if x.isalnum()]) + self.ticket_reference.strip()
        hsh = hashlib.sha512()
        hsh.update(hash_this.encode("utf-8"))
        self.hash = base64.urlsafe_b64encode(hsh.hexdigest().encode("utf-8"))[:6].decode("utf-8").upper()
        # uuid for webservice
        self.uuid = str(UUID4(hsh.hexdigest()[:32]))


class Attendees:
    def __init__(self, xlsx_file: Path, columns: dict[str, str], select_func: Callable | None = None,
                 transforms: dict[str, Callable] | None = None):
        self.attendees = []
        self.xlsx_file = xlsx_file
        self.columns = columns
        self.select_func = select_func
        self.transforms = transforms

        self.attendees = self.load_attendees()

    def load_attendees(self) -> list[Attendee]:
        df = pd.read_excel(self.xlsx_file, dtype=str)
        logger.info(f"Loaded {len(df)} attendees from {self.xlsx_file}")

        # appy optional method to select rows based on the data, e.g., remove non-participants
        if self.select_func is not None:
            df = self.select_func(df)
        logger.info(f"Applied selecting attendees: {len(df)} attendees in list.")

        # transformations apply methods to mangle column data
        for col in self.transforms:
            df[col] = df[col].apply(self.transforms[col])
        logger.info(f"Transformed {len(df)} attendees")

        # remove incomplete information, i.e., missing name or email; other columns are populated by default.
        df = df[self.columns.keys()]
        df = df.dropna(how="any")
        logger.info(f"Dropped any record with missing info: {len(df)} attendees in list.")

        # avoid sending multiple certificates if people have multiple tickets, e.g., day tickets.
        df["unique"] = df["Ticket Full Name"] + df["Ticket Email"]
        df = df.drop_duplicates(subset="unique")
        df = df.drop(columns=["unique"])
        logger.info(f"Removed duplicates (same name, email combination): {len(df)} attendees in list.")

        logger.info("Creating attendees list.")
        attendees = []
        for record in df.to_dict(orient="records"):
            try:
                # noinspection PyArgumentList
                attendees.append(Attendee(**{self.columns[k]: v for k, v in record.items()}))  # noqa: C408
            except Exception as e:
                logger.error(f"Error creating attendee {record} {e}")
        logger.info(f"Finally {len(df)} attendees in list.")

        return attendees
