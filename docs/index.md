# 🎨 Design & 🚢 Ship 📜 PDFs

Create signed, secure PDFs easy to validate.

This is a boilerplate repository.

|                         | What does that mean?                               |
|-------------------------|----------------------------------------------------|
| signed                  | PDFs are digitally signed and cannot be altered    |  
| secure                  | disallow features like copying text, altering      |                            | 
| validated via a website | A link to your website to confirm the authenticity |

The PDFs that can be used e.g., for

- issuing certificates of attendance for a conference
- issuing certificates of participation or a training
- vouchers
- …

This repo will be help you with the generation of the certificates but does require:

- Code to mangle/ prepare the data to be displayed on the certificate
- Configuration to create the layout of the PDF
- Generation of a personal PKCS12 certificate to sign the PDFs
- Customizing the upload script to fit your own website
- Customizing the delivery email script

Main library used: [fpdf2](https://py-pdf.github.io/fpdf2/index.html)

Sample PDF  
<img src="graphics/example_certificate.png" style="width: 75%;">

Sample Website for Validation  
<img src="graphics/example-validation.png" style="width: 75%;">


## ⭐️ Four-Step Process

1. Prepare data to be included in the certificate
2. Generate PDF certificates
3. Upload PDF certificates to the website
4. Send emails to notify recipients

Each step should be run separately for review of intermediate results.


## Realization

[Pioneers Hub](https://www.pioneershub.org/en/) helps to build and maintain thriving communities of experts in tech and
research to share knowledge, collaborate and innovate together.
![Pioneers Hub Logo](assets/images/Pioneers-Hub-Logo-vereinfacht-inline.svg)