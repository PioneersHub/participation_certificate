# Email branding assets

Assets used by the HTML certificate-delivery emails (see
[`participation_certificate/email_templates/`](../../participation_certificate/email_templates/)).

Two files live in this directory:

| File | Role |
| --- | --- |
| `PyConDE PyData 2026 Logo dark blue_03.png` | **Master copy** of the chosen variant — kept verbatim, as exported from the Media Kit. Never sent over the wire. |
| `pyconde-pydata-2026-logo.png` | **Working copy** sent as an inline CID image on every email. Downscaled from the master to retina-appropriate dimensions. |

The HTML templates reference the working copy by Content-ID:

```html
<img src="cid:pyconde-pydata-2026-logo.png" alt="PyCon DE & PyData 2026">
```

Mailgun assigns the bare filename as the `Content-ID`, so the HTML reference must match the filename of the working copy exactly. `branding.logo_path` in `config.yaml` points at `assets/email/pyconde-pydata-2026-logo.png`.

## Variant chosen

`PyConDE PyData 2026 Logo dark blue_03.png` — Dark Blue on white, variant `_03`. Operator note: the `_03` spacing is better suited for email than `_01`. The Media Kit source on Google Drive stays untouched; only this local copy is in scope for resampling.

## Regenerate the working copy

Re-run after any change to the master file (different variant, updated artwork). Uses macOS `sips` (always present, no Homebrew dependency):

```bash
sips --resampleWidth 880 \
  "assets/email/PyConDE PyData 2026 Logo dark blue_03.png" \
  --out assets/email/pyconde-pydata-2026-logo.png
```

`--resampleWidth` preserves the aspect ratio. The PNG alpha channel and color profile are preserved as well.

### Why width 880?

HTML templates render the logo at `<img width="220">`. At retina (2×) the source needs ~440 px; rounded up to 880 px so a non-retina client downscales by a clean factor of 4. The on-disk working copy ends up around **880 × 338 px**, ~60 KB — well under Gmail's 102 KB message-clipping threshold.

### Optional: shrink further

If the working copy lands over 100 KB after `sips`, run a PNG optimiser:

```bash
pngcrush -ow -brute assets/email/pyconde-pydata-2026-logo.png   # if installed
# or
oxipng -o max --strip safe assets/email/pyconde-pydata-2026-logo.png  # if installed
```

Both preserve pixels and alpha; expect 30–60 % shrink.

## Brand reference (from the Media Kit Manual)

Used by the HTML templates:

| Token | Value | Where |
| --- | --- | --- |
| Primary | `#3778be` (dark blue) | Top rule, link colour |
| Accent | `#fac800` (yellow) | CTA button background |
| Body | `#3a3f43` (charcoal) | Paragraph text |
| Footer | `#b7bcbf` (silver) | Footer rule + footer text |
| Type | `Helvetica, Arial, sans-serif` | All copy |

Logo clearspace: at least one logo-height on every side. Email header CSS width is `220 px`; do not scale below `160 px`.

## Source

`/Users/hendorf/Library/CloudStorage/GoogleDrive-alexander@pioneershub.org/Shared drives/PioneersHub/PyCon/2026/DESIGN 2026/Media Kit/Logo/`

> Do not resize, recolour, or re-export the Media Kit source. The master copy in this directory is the canonical local artefact; resampling happens only on the working copy.
