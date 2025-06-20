# Data Input Guide

This guide explains how to prepare and input attendee data for certificate generation.

## Overview

The certificate generation system processes attendee data from Excel files (`.xlsx`) by default. The data goes through several stages:

1. **Loading** - Read data from Excel file
2. **Selection** - Filter out non-participant records
3. **Transformation** - Apply data transformations
4. **Validation** - Remove incomplete records and duplicates
5. **Model Creation** - Convert to `Attendee` objects

## Data Format Requirements

### File Format

- **Default**: Excel file (`.xlsx`)
- **Location**: Place your data file in the `_data/` directory
- **Naming**: Use a descriptive name like `attendees-eventname-year.xlsx`

### Required Columns

Your Excel file must contain these columns:

| Column Name | Description | Example | Maps to |
|-------------|-------------|---------|---------|
| **Ticket Full Name** | Complete name of the attendee | "Jane Smith" | `full_name` |
| **Ticket First Name** | First name only | "Jane" | `first_name` |
| **Ticket Email** | Valid email address | "jane.smith@example.com" | `email` |
| **Ticket Reference** | Unique ticket identifier | "ABCD-1234" | `ticket_reference` |
| **Ticket** | Ticket type (will be transformed) | "Conference Pass - On Site" | `attended_how` (transforms to "on site" or "remotely") |

**Important**: The `Ticket` column is transformed into the `attended_how` field, which must be either:
- `"on site"` - for in-person attendance
- `"remotely"` - for online/virtual attendance

The default transformation rule: if the ticket type contains "online" (case-insensitive), it becomes "remotely", otherwise "on site".

### Additional Columns for Filtering

If your data includes non-participant tickets, include:

| Column Name | Description | Purpose |
|-------------|-------------|---------|
| **Void Status** | Ticket cancellation status | Filter out "voided" tickets |

## Data Preparation Steps

### 1. Create Your Excel File

Create an Excel file with the required columns. A sample CSV template is available at `_data/attendee_template.csv`.

Here's a sample structure:

```
| Ticket Full Name | Ticket First Name | Ticket Email | Ticket Reference | Ticket | Void Status |
|------------------|-------------------|--------------|------------------|---------|-------------|
| Jane Smith | Jane | jane@example.com | CONF-001 | Conference Pass | |
| John Doe | John | john@example.com | CONF-002 | Online Ticket | |
| Alice Johnson | Alice | alice@example.com | SOCIAL-001 | Social Event | |
| Bob Wilson | Bob | bob@example.com | CONF-003 | Conference Pass | voided |
```

### 2. Configure Data Loading

Edit `participation_certificate/run.py` to match your data:

```python
# File to load the data from
attendees_table = "your-event-attendees.xlsx"

# Map your Excel columns to the required fields
load_columns = {
    "Ticket Full Name": "full_name",
    "Ticket First Name": "first_name",
    "Ticket Email": "email",
    "Ticket Reference": "ticket_reference",
    "Ticket": "attended_how",
}
```

### 3. Customize Data Selection (Optional)

Filter out non-participant records:

```python
def select_rows(data_frame: pd.DataFrame) -> pd.DataFrame:
    """Remove rows that are not participants"""
    # Example: Filter out social events, luggage, childcare tickets
    data_frame = data_frame[
        ~data_frame["Ticket"].str.contains("Social|luggage|Childcare|Keynote|TEST")
    ].reindex()

    # Example: Remove cancelled tickets
    data_frame = data_frame[~data_frame["Void Status"].fillna("").str.contains("voided")]

    return data_frame
```

### 4. Apply Data Transformations (Optional)

Transform column values as needed:

```python
# Example: Convert ticket types to attendance method
# The attended_how field must be either "on site" or "remotely"
transformers = {
    "Ticket": lambda x: "remotely" if "online" in x.lower() else "on site"
}
```

## Alternative Data Sources

### Loading from CSV

```python
import pandas as pd
from pathlib import Path

# Load from CSV instead of Excel
df = pd.read_csv(Path(__file__).parents[1] / "_data" / "attendees.csv")
# Continue with same ProcessAttendees workflow
```

### Loading from API

```python
import requests
import pandas as pd

# Fetch data from API
response = requests.get("https://api.example.com/attendees")
data = response.json()

# Convert to DataFrame
df = pd.DataFrame(data)
# Map API fields to required columns
df = df.rename(columns={
    "name": "Ticket Full Name",
    "firstName": "Ticket First Name",
    "email": "Ticket Email",
    # etc.
})
```

### Loading from Database

```python
import pandas as pd
import sqlalchemy

# Connect to database
engine = sqlalchemy.create_engine('postgresql://user:pass@host/db')

# Query attendees
query = """
    SELECT
        full_name as "Ticket Full Name",
        first_name as "Ticket First Name",
        email as "Ticket Email",
        ticket_id as "Ticket Reference",
        ticket_type as "Ticket"
    FROM attendees
    WHERE event_id = 123
"""
df = pd.read_sql_query(query, engine)
```

## Data Validation

The system automatically handles:

1. **Missing Data** - Records with missing name or email are removed
2. **Duplicates** - Multiple tickets for the same person (name + email) are consolidated
3. **Email Validation** - Invalid email addresses will cause an error

## Common Issues and Solutions

### Issue: Column Not Found
**Error**: `KeyError: 'Ticket Full Name'`
**Solution**: Check your Excel column names match exactly (including spaces and capitalization)

### Issue: No Attendees Loaded
**Cause**: All records filtered out by selection function
**Solution**: Review your filter criteria and check the data

### Issue: Email Validation Errors
**Error**: `validation error for Attendee`
**Solution**: Check for invalid email formats in your data

### Issue: File Not Found
**Error**: `FileNotFoundError`
**Solution**: Ensure file is in `_data/` directory and path is correct

## Example: Complete Configuration

Here's a complete example for a conference:

```python
# participation_certificate/run.py

# Data file
attendees_table = "pycon-2024-attendees.xlsx"

# Column mapping
load_columns = {
    "Full Name": "full_name",
    "First Name": "first_name",
    "Email Address": "email",
    "Order Reference": "ticket_reference",
    "Ticket Type": "attended_how",
}

# Row selection
def select_rows(data_frame: pd.DataFrame) -> pd.DataFrame:
    # Keep only conference attendees
    valid_tickets = data_frame[
        data_frame["Ticket Type"].str.contains("Conference|Workshop", case=False)
    ]
    # Remove cancelled
    valid_tickets = valid_tickets[
        valid_tickets["Status"] != "Cancelled"
    ]
    return valid_tickets

# Data transformation
transformers = {
    "Ticket Type": lambda x: "on site" if "in-person" in x else "online"
}
```

## Next Steps

After preparing your data:

1. Configure your certificate design in `config_local.yaml`
2. Run the certificate generation script
3. Review generated PDFs in `_certificates/` directory

For more details, see the [Complete Walkthrough](walkthrough.md).
