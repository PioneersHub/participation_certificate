# PDF Background Feature Documentation

## Overview

The PDF background feature allows you to use a professionally designed PDF as a background template for certificates, instead of generating backgrounds with colored rectangles. This enables complex designs, gradients, watermarks, and other graphical elements that would be difficult to create programmatically.

## Configuration

### Basic Setup

Add the following configuration to your `config_local.yaml`:

```yaml
layout:
  pdf_background:
    enabled: true  # Enable PDF background feature
    file: "your-background.pdf"  # Filename relative to graphics directory
    page: 1  # Which page to use from multi-page PDFs (1-based index)
```

### Example Configuration

```yaml
layout:
  pdf_background:
    enabled: true
    file: "your-conference-background.pdf"
    page: 1

  # When pdf_background is enabled, the background rectangles are ignored
  background:
    # These colored rectangles will be skipped when using PDF background
    - color: [61, 164, 51]
      width: 0
      height: 0
      position: [0, 0]
```

## How It Works

1. **Background PDF Loading**: The system loads the specified PDF from the `graphics` directory
2. **Overlay Generation**: Text and graphics are generated as a transparent overlay using fpdf2
3. **PDF Merging**: The overlay is merged with the background using pikepdf
4. **Security & Metadata**: Encryption, permissions, and metadata are applied to the final PDF

## File Structure

```text
participation_certificate/
├── graphics/
│   ├── your-conference-background.pdf  # Background PDF
│   ├── logo.png                                      # Overlay graphics
│   └── signature.png                                 # Overlay graphics
├── config_local.yaml                                 # Your configuration
└── _certificates/                                    # Output directory
```

## Features

### Advantages

- **Professional Designs**: Use designer-created templates
- **Complex Backgrounds**: Support for gradients, patterns, watermarks
- **Performance**: Pre-rendered backgrounds are faster than generating
- **Flexibility**: Different backgrounds for different events
- **Backwards Compatible**: Existing colored rectangle backgrounds still work

### Limitations

- Background PDF must be in the `graphics` directory
- Only one page can be used as background (specified by `page` parameter)
- Digital signatures may need additional configuration with pikepdf

## Migration Guide

### From Colored Rectangles to PDF Background

1. **Prepare your background PDF**
   - Design your certificate background in any design tool
   - Export as PDF (A4 landscape recommended)
   - Place in the `graphics` directory

2. **Update configuration**

   ```yaml
   layout:
     pdf_background:
       enabled: true
       file: "your-background.pdf"
       page: 1
   ```

3. **Remove PDF from graphics list**

   If you were previously including the PDF as a graphic element, remove it:

   ```yaml
   graphics:
     # Remove this entry:
     # - name: "your-background.pdf"
     #   position: [0, 0]
     #   width: 841
   ```

## Troubleshooting

### Background PDF not found

- Ensure the PDF exists in the `graphics` directory
- Check the filename spelling in configuration
- Verify the path: `graphics/your-background.pdf`

### Text not visible on background

- Adjust text colors to contrast with the background
- Check text positions to ensure they're within page bounds
- Verify font colors in configuration

### Performance issues

- Optimize background PDF file size
- Use simpler PDF structures when possible
- Consider caching for large batch generation

## Example Use Cases

1. **Conference Certificates**: Professional backgrounds with event branding
2. **Training Certificates**: Corporate templates with logos and watermarks
3. **Academic Certificates**: Official templates with security features
4. **Event Vouchers**: Decorative backgrounds with unique designs

## Testing

To test the PDF background feature:

```python
from participation_certificate import conf

# Check if PDF background is enabled
if conf.layout.pdf_background.get('enabled'):
    print(f"Using PDF background: {conf.layout.pdf_background.file}")
else:
    print("Using colored rectangle backgrounds")
```

## Future Enhancements

Potential improvements for future versions:

- Support for multiple background templates based on conditions
- Dynamic background selection based on attendee attributes
- Background scaling and positioning options
- Support for PDF forms and fillable fields
