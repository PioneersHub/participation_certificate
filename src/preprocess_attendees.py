from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd

from src import logger
from src.models.attendee import Attendee


class ProcessAttendees:
    """ Process data to fit the Attendee model."""
    def __init__(
            self,
            xlsx_file: Path,
            columns: dict[str, str],
            select_func: Callable[[..., pd.DataFrame], pd.DataFrame] | None = None,
            transformers: dict[str, Callable[[..., Any], Any]] | None = None
    ):
        self.attendees = []
        self.xlsx_file = xlsx_file
        self.columns = columns
        self.select_func = select_func
        self.transformers = transformers

        self.attendees = self.load_attendees()

    def load_attendees(self) -> list[Attendee]:
        df = pd.read_excel(self.xlsx_file, dtype=str)
        logger.info(f"Loaded {len(df)} attendees from {self.xlsx_file}")

        # appy optional method to select rows based on the data, e.g., remove non-participants
        if self.select_func is not None:
            df = self.select_func(df)
        logger.info(f"Applied selecting attendees: {len(df)} attendees in list.")

        # transformations apply methods to mangle column data
        for col in self.transformers:
            df[col] = df[col].apply(self.transformers[col])
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
