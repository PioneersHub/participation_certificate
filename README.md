# Certificate of Participation

Create signed certificates of participation that can be validate via a website.

## Four-Step Process

1. Prepare attendees' data
2. Generate certificates
3. Upload certificates to the website
4. Send emails to attendees

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

See [Certbot](//--> ADD LINK  <--- //) how to create certificates with certbot.
A `privateKey` and a `certificate` is created.

To create a signature for the signing the PDfs use the following command
to create the certificate to sign the PDFs.
```shell
openssl pkcs12 -export -out YourCertificateToSignPDFs.p12 -inkey privateKey.pem -in certificate.crt
```

More options to create certificates are described 
[in this post](https://erolyapici.medium.com/how-to-generate-a-pkcs-12-file-1f4c8307aa7c).


### 3. Upload certificates to the website

// --> TODO

### 4. Send emails to attendees

// --> TODO


### Tipps and Best Practices.

#### Designing the Certificate: Layouting

The layout is created by drawing elements on a canvas.
Elements are placed on the canvas by assigning them coordinates.
This can be time-intensive and try-and-error.

Design a layout, save it as background in the beginning and place elements accordingly.

#### Designing the Certificate: Elements

#### Design vs. Signing and Encryption

A convenient way to design certificates is use to a PDF with a generic layout
(e.g., designed in a design application), create a new PDF with the individual information
and merge both to a new PDF.

//---> ADD LINK to fdpf page <----//

Downside: PDF created this way can **not** be signed or encrypted.