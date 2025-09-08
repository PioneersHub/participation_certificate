## 🏭 Walkthrough Example

**Certificate of Attendance for a Conference**

We want to create certificates for attendees of the "PyCon DE & PyData Berlin 2024" conference.
We have a list of all tickets sold including the names of the participants.

### 0. Configuration

Configuration is done in the `config.yaml` and `config_local.yaml` files.
Any key in `config_local.yaml` will overwrite the key in `config.yaml`.

Use `config_local.yaml` for your local settings, do not change `config.yaml`.

### 1. Prepare attendees' data

The system needs attendee data to generate certificates. Each certificate requires one `Attendee` instance (a [pydantic](https://pydantic.dev) model).

#### Data Input Methods

**Option 1: Excel File (Default)**
```python
# Place your Excel file in _data/ directory
attendees_table = "attendees-pyconde-2024.xlsx"

# Map Excel columns to required fields
load_columns = {
    "Ticket Full Name": "full_name",
    "Ticket First Name": "first_name",
    "Ticket Email": "email",
    "Ticket Reference": "ticket_reference",
    "Ticket": "attended_how",
}
```

**Option 2: CSV File**
```python
import pandas as pd
df = pd.read_csv("_data/attendees.csv")
# Apply same column mapping and processing
```

**Option 3: API Data**
```python
import requests
response = requests.get("https://your-api.com/attendees")
attendees_data = response.json()
# Convert to DataFrame and process
```

#### The Attendee Model

```python
class Attendee(BaseModel):
    full_name: str           # Full name for the certificate
    first_name: str          # First name for personalization
    email: EmailStr          # Valid email for delivery
    ticket_reference: str    # Unique ticket ID
    attended_how: str        # Must be either "on site" or "remotely"
    hash: str | None = None  # Auto-generated unique hash
    uuid: str | None = None  # Auto-generated UUID
```

#### Data Processing Pipeline

1. **Load**: Read from your data source
2. **Filter**: Remove non-participants (social events, cancelled tickets)
3. **Transform**: Standardize values (e.g., "Online Ticket" → "remotely")
4. **Validate**: Remove incomplete records
5. **Deduplicate**: One certificate per person (name + email combination)

Example: See `participation_certificate/preprocess_attendees.py` and the [Data Input Guide](data-input.md) for detailed instructions.

Output: `list[Attendee]`

### 2. Generate certificates

Input: `list[Attendee]`

Steps to generate PDFs:

1. Design: drawing the generic elements in the PDF.
2. Design: place attendee information
3. Create PDF, set rights (e.g., disallow modifications) and sign digitally.
4. PDFs are saved in the `/_certificates/<<event>>` directory which is create automatically

#### Locations

| what            | location                              | remarks                         |
|-----------------|---------------------------------------|---------------------------------|
| custom fonts    | `/fonts/<font family name>` directory | load them before usage          |
| graphics        | `/graphics`                           |                                 |
| signature files | `/_signatures`                        | make sure to never share/commit |

Example: `[generate_certificates.py](src/generate_certificates.py)`

Uses: https://py-pdf.github.io/fpdf2/

#### Certificate to sign PDFs

Certificates issued need to be trustable and protected against alterations.

For protection, the certificates are signed with a PKCS12 certificate.

##### Best Practice

Use an unique subdomain, e.g. `certificates.your-domain.abc`.
In you do not have a certificate for this domain, yet,
create a free certificate for this domain with `certbot`.


See [Certbot](https://certbot.eff.org) how to create certificates with certbot.
A `privateKey` and a `certificate` is created.

To create a signature for the signing the PDfs use the following command
to create the certificate to sign the PDFs.

```shell
openssl pkcs12 -export -out YourCertificateToSignPDFs.p12 -inkey privateKey.pem -in certificate.crt
```

More options to create certificates are described
[in this post](https://erolyapici.medium.com/how-to-generate-a-pkcs-12-file-1f4c8307aa7c).

### 3. Upload certificates for Download and Validation Pages to the Conference Website

Certificates are accompanied by a JSON that contains all the attendee information.

Example: `./participation_certificate/valdiation_upload.py`

Generates markdown files that can be added to the static website renderer (PyCon DE uses lektor).

PDF files are stored in a static website S3 bucket for download. Upload is done manually :D.

### 4. Send emails to attendees

To share the certificates with the attendees, send them an email with the download link.

Example: send_certificates.py

Uses the helpdesk.com API to send emails via helpdesk tickets.
DEPRECATED: the helpdesk.com API is throttled (ending mass info takes too long) and will be replace in the future.
