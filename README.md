# Certificate of Participation

Signed certificates of participation.

## Four-Step Process

1. Prepare attendees' data
2. Generate certificates
3. Upload certificates to the website
4. Send emails to attendees

### 1. Prepare attendees' data

Example: `[preprocess_attendees.py](src%2Fpreprocess_attendees.py)`

Output: `list[Attendee]`

### 2. Generate certificates

Input: `list[Attendee]`

Generate PDFs:
- Design
- Attendee information
- Disallow any modifications
- Digital signature

Put fonts in `/fonts` directory.   
Put graphics in `/graphics` directory.  
Put signature files in `/_signatures` directory.


Example: `[generate_certificates.py](src%2Fgenerate_certificates.py)`

Uses: https://py-pdf.github.io/fpdf2/

#### Certificate to sign PDFs
https://erolyapici.medium.com/how-to-generate-a-pkcs-12-file-1f4c8307aa7c

##### Purchase a certificate issued by a known certificate authority
   One approach to obtaining a certificate involves the procurement of a certificate from a reputable Certificate
   Authority (CA) through a monetary transaction. This involves the subsequent amalgamation of the purchased public
   certificate with its corresponding private key. Alternatively, for those seeking a cost-free option, Let’s Encrypt
   provides a service that issues SSL/TLS certificates without charge. In such instances, the acquired public
   certificate from Let’s Encrypt is combined with its associated private key, resulting in the creation of a PKCS #12
   file as a no-cost alternative for certificate generation.

> openssl pkcs12 -export -out keyStore.p12 -inkey privateKey.pem -in certificate.crt

### 3. Upload certificates to the website

### 4. Send emails to attendees
