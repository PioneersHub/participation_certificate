"""Alter config on run
https://www.mkdocs.org/user-guide/configuration/#hooks
"""

from datetime import datetime


def on_config(config, **kwargs):  # noqa: ARG001
    base_year = 2024
    current_year = datetime.now().year
    year_range = f"{base_year}-{current_year}" if current_year > base_year else str(base_year)
    config.copyright = (
        f"Copyright © {year_range} Pioneers Hub gGmbH – "
        f'<a href="#__consent">Change cookie settings</a>'
    )
