# Certificate of Participation

This is a boilerplate repo to create signed certificates of participation that can be validated via a website.  
It's supposed to be help you with the generation of the certificates but does require:

- Code mangling to prepare the data to be displayed on the certificate
- Designing / altering the example certificate layout
- Generation of a custom PKCS12 certificate to sign the PDFs
- Customizing the upload script to fit your website
- Customizing the delivery email script

Main library used: [fpdf2](https://py-pdf.github.io/fpdf2/index.html)

## Four-Step Process

1. Prepare attendees' data
2. Generate certificates
3. Upload certificates to the website
4. Send emails to attendees

Each step should be run separately for review of intermediate results.

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

Certificates are accompanied by a json that contains all the attendee information.

Example: [valdiation_upload.py](src%2Fvaldiation_upload.py)

Generates markdown files that can be added to the static website renderer (PyCon DE uses lektor).

PDF files are stored in an static website S3 bucket for download. Upload is done manually :D.

### 4. Send emails to attendees

To share the certificates with the attendees, send them an email with the download link.

Example: send_certificates.py

Uses the helpdesk.com API to send emails via helpdesk tickets.
DEPRECATED: the helpdesk.com API is throttled (ending mass info takes too long) and will be replace in the future.

### Tipps and Best Practices.

#### Designing the Certificate: Layouting

The layout is created by drawing elements on a canvas.
Elements are placed on the canvas by assigning them coordinates.
This can be time-intensive and try-and-error.

Design a layout, save it as background in the beginning and place elements accordingly.

#### Designing the Certificate: Elements

Adding new elements will add them on top of existing elements at the coordinates.

Consider there is a header and footer section in the document canvas by default.
To content or change these sections one needs to overwrite the `header` and `footer` methods:

```python
# create and use a new class that inherits from FPDF
class PDF(FPDF):
    def header(self):
        pass  # do your stuff

    def footer(self):
        pass  # do your stuff
```

#### Design vs. Signing and Encryption

A convenient way to design certificates is use to a PDF with a generic layout
(e.g., designed in a design application), create a new PDF with the individual information
and merge both to a new PDF.

See [Adding content onto an existing PDF page](https://py-pdf.github.io/fpdf2/CombineWithPdfrw.html#adding-content-onto-an-existing-pdf-page)

Downside: PDF created this way can **not** be signed or encrypted.

#### Markdown in text for PDFs

You can use markdown in the text for the PDFs.
Make sure to load fonts for bold and italic text like:  

regular-text-font-name, typeface, path-to-font-file, e.g.,

```python
fpdf.add_font("poppins-regular", "B", font.parents[1] / "Poppins/Poppins-Bold.ttf")
```