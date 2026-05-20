# Branding — per-project logo

Every project's email branding lives in
`projects/${CERTIFICATE_PROJECT_SLUG}/branding/`. The repo ships no event-specific
assets at the root anymore.

| File | Role |
| --- | --- |
| `branding/logo.png` | **Working copy**, sent as an inline (CID) image on every email. PNG, RGBA, ~880 px wide, < 100 KB. Standardised filename so the HTML layout's `<img src="cid:logo.png">` matches without per-event template tweaks. |
| `branding/master.png` *(optional)* | Full-resolution master from the Media Kit, kept verbatim. Never sent over the wire — the working copy is resampled from it. |

`branding.logo_path` in the project's `config.yaml` points at the working copy:

```yaml
branding:
  logo_path: "branding/logo.png"
```

## Why the filename is `logo.png`, not `<event>-logo.png`

Mailgun uses the bare filename of an inline attachment as the `Content-ID`. The
shared HTML layout (`participation_certificate/email_templates/layout.html`)
references `<img src="cid:logo.png" …>`. Keeping the working-copy filename
canonical means every project's logo "just works" — no per-event template
overrides, no per-event CID string in code.

## Drop a new logo in

1. Place the master file at `projects/<slug>/branding/master.png`.
2. Resample to the email-display size (preserves aspect, keeps alpha):

   ```bash
   sips --resampleWidth 880 \
       projects/<slug>/branding/master.png \
       --out projects/<slug>/branding/logo.png
   ```

   Target: ~880 × proportional px, RGBA PNG, < 100 KB. Twice the rendered
   CSS width (220 px) so retina clients downscale cleanly to 2× crisp.

3. Optional shrink (only if `sips` lands you over 100 KB):

   ```bash
   pngcrush -ow -brute projects/<slug>/branding/logo.png   # if installed
   # or
   oxipng -o max --strip safe projects/<slug>/branding/logo.png  # if installed
   ```

4. Send one smoke email and confirm the logo renders inline in your inbox:

   ```bash
   CERTIFICATE_PROJECT_SLUG=<slug> uv run python participation_certificate/deliver_certificates.py \
       --type attendee --limit 1 --override-recipient you@example.com
   ```

## Brand tokens used in the HTML layout

The shared HTML layout hard-codes the brand-token palette below. To re-brand
for a different conference, edit
`participation_certificate/email_templates/layout.html` once (the colours are
inline-CSS literals; not yet config-driven).

| Token | Value | Where |
| --- | --- | --- |
| Primary | `#3778be` (dark blue) | Top rule, link colour |
| Accent | `#fac800` (yellow) | CTA button background |
| Body | `#3a3f43` (charcoal) | Paragraph text |
| Footer | `#b7bcbf` (silver) | Footer rule + footer text |
| Type | `Helvetica, Arial, sans-serif` | All copy |

Logo clearspace: at least one logo-height on every side. Email-header CSS
width is `220 px`; do not scale below `160 px`.
