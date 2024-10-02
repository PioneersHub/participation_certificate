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