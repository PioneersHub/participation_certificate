## 🏭 Walkthrough Example

**Certificate of Attendance for a Conference**

We want to create certificates for attendees of the "PyCon DE & PyData Berlin 2024" conference.  
We have a list of all tickets sold including the names of the participants.

### 0. Configuration

Configuration is done in the `config.yaml` and `config_local.yaml` files.
Any key in `config_local.yaml` will overwrite the key in `config.yaml`.

Use `config_local.yaml` for your local settings, do not change `config.yaml`.

### 1. Prepare attendees' data

Preprocess data: per certificate create one `Attendee`  instance.  
`Attendee` is a [pydantic](https://pydantic.dev) model.

```python
# noinspection PyUnresolvedReferences,PyUnboundLocalVariable
class Attendee(Attendee):
    full_name: str
    first_name: str
    email: EmailStr
    ticket_reference: str
    attended_how: str
    hash: str | None = None
    uuid: str | None = None
```

Example: `[preprocess_attendees.py](src%2Fpreprocess_attendees.py)`

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

Example: `[generate_certificates.py](src%2Fgenerate_certificates.py)`

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
