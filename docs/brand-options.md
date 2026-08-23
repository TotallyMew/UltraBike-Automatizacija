# Brand Options Reference

This document outlines all available brand-specific options that can be passed via `brand_options` parameter to product uploaders.

## Universal Options (All Brands)

These options are supported by **all brand uploaders** via the `BaseUploader` class:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `description_name` | `str \| None` | `None` | Custom description template to use from database instead of scraping brand website. If `None`, scrapes from brand website. |
| `append_disclaimer` | `bool` | `False` | Appends standard disclaimer text to the product description (main description field). |
| `append_order_note` | `bool` | `False` | Appends order information to the short description field (displayed on product cards). |

### Example Usage:

```python
brand_options = {
    "description_name": "Standard Mountain Bike Template",
    "append_disclaimer": True,
    "append_order_note": True
}

uploader = Pinarello(
    driver=driver,
    brand_name="PINARELLO",
    product_code="F5-DISK-2024",
    url_or_code="https://pinarello.com/...",
    db_manager=db,
    brand_options=brand_options
)
```

---

## Brand-Specific Options

### Pinarello

**Additional Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `frameset_only` | `bool \| None` | `None` | Controls whether to scrape complete bike or frameset-only version. If `None`, scraper auto-detects based on URL. |

**Implementation Location:** [Uploaders/Pinarello.py:9](Uploaders/Pinarello.py#L9)

**Example:**

```python
brand_options = {
    "frameset_only": True,  # Force frameset-only scraping
    "description_name": "Premium Road Frameset",
    "append_disclaimer": True
}

uploader = Pinarello(
    brand_name="PINARELLO",
    product_code="F5-FRAMESET",
    url_or_code="https://pinarello.com/f5-frameset",
    brand_options=brand_options
)
```

**Why `frameset_only` exists:**
- Pinarello sells both complete bikes and framesets separately
- Same product code may have different configurations (complete vs frameset)
- Scraper needs to know which variant to extract from the website

---

### Rascal

**Additional Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `variant_index` | `int \| None` | `None` | Selects specific variant when product page contains multiple variants. Currently hardcoded to `None` (not exposed in GUI). |

**Implementation Location:** [Uploaders/Rascal.py:9](Uploaders/Rascal.py#L9)

**Current Behavior:**
- `variant_index` is always `None` (not exposed in GUI)
- If product page has multiple variants, scraper raises an error
- User must manually select correct variant URL

**Future Enhancement:**
```python
# Potential future GUI implementation
brand_options = {
    "variant_index": 2,  # Select 3rd variant (0-indexed)
    "description_name": "Kids Bike Template"
}
```

**Why `variant_index` exists:**
- Rascal Bikes product pages sometimes list multiple color/size variants
- Scraper needs to know which variant to extract
- Currently not implemented in GUI (planned feature)

---

### Other Brands

The following brands **only** use universal options (no brand-specific options):

- **TREK**
- **Rondo**
- **Factor**
- **KROSS**
- **Basso**
- **Lee Cougan**
- **Octane**

**Example for standard brands:**

```python
brand_options = {
    "description_name": "Mountain Bike Standard",
    "append_disclaimer": False,
    "append_order_note": True
}

uploader = Trek(
    brand_name="TREK",
    product_code="FUEL-EX-9.8",
    url_or_code="https://www.trekbikes.com/...",
    brand_options=brand_options
)
```

---

## Option Processing Pipeline

### 1. GUI Layer ([GUI_Qt/screens/BatchUploadScreen.py](GUI_Qt/screens/BatchUploadScreen.py))

User selects options in batch upload dialog:
- Description template dropdown
- Disclaimer checkbox
- Order note checkbox
- Brand-specific options (if applicable)

```python
brand_options = {
    "description_name": description_name or None,
    "frameset_only": bool(frameset_only) if frameset_only is not None else False,
    "append_disclaimer": bool(append_disclaimer),
    "append_order_note": bool(append_order_note)
}
```

### 2. Batch Processor ([Utilities/BatchProcessor.py:48-95](Utilities/BatchProcessor.py#L48-L95))

Normalizes string values to proper types:

```python
def add_to_queue(self, brand, product_code, url_or_code, brand_options=None):
    # Normalize description_name (strip empty strings → None)
    description_name = brand_options.get("description_name")
    if isinstance(description_name, str):
        description_name = description_name.strip()
        if description_name == "":
            description_name = None

    # Normalize boolean options (handle "yes"/"true"/"1" strings)
    append_disclaimer = brand_options.get("append_disclaimer", False)
    if isinstance(append_disclaimer, str):
        append_disclaimer = append_disclaimer.strip().lower() in ("yes", "true", "1")
    else:
        append_disclaimer = bool(append_disclaimer)

    # ... similar normalization for append_order_note
```

### 3. Base Uploader ([Uploaders/BaseUploader.py](Uploaders/BaseUploader.py))

Receives normalized options and passes to description manager:

```python
def __init__(self, brand_options=None, ...):
    self.brand_options = brand_options or {}

    # Extract universal options
    self.description_name = self.brand_options.get('description_name', None)
    self.append_disclaimer = self.brand_options.get('append_disclaimer', False)
    self.append_order_note = self.brand_options.get('append_order_note', False)
```

### 4. Brand Uploader (e.g., [Uploaders/Pinarello.py](Uploaders/Pinarello.py))

Extracts brand-specific options and passes to scraper:

```python
def scrape(self):
    frameset_only = self.brand_options.get('frameset_only', None)

    self.translationManager.prepareTranslationFiles(
        scrape_func=scrapeAndTranslateToFilePinarello,
        url=self.bicycleUrlOrCode,
        frameset_only=frameset_only  # Pass to scraper
    )
```

---

## Validation Rules

### Type Conversion

All options undergo automatic type conversion:

| Input Type | Converts To | Example |
|------------|-------------|---------|
| `"yes"`, `"true"`, `"1"` | `True` | `"yes"` → `True` |
| `"no"`, `"false"`, `"0"` | `False` | `"no"` → `False` |
| `""` (empty string) | `None` | `""` → `None` |
| Whitespace-only string | `None` | `"   "` → `None` |

### Default Values

If an option is not provided:

```python
brand_options = {}  # Empty dict

# Results in:
description_name = None
append_disclaimer = False
append_order_note = False
frameset_only = None  # Pinarello only
variant_index = None  # Rascal only
```

---

## Adding New Brand-Specific Options

To add a new brand-specific option:

### 1. Update Brand Uploader

```python
# Uploaders/YourBrand.py
class YourBrand(ProductUploader):
    def scrape(self):
        # Extract your custom option
        custom_option = self.brand_options.get('custom_option', default_value)

        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeYourBrand,
            url=self.bicycleUrlOrCode,
            custom_option=custom_option  # Pass to scraper
        )
```

### 2. Update Scraper

```python
# Scrapers/YourBrandScraper.py
def scrapeYourBrand(bicycleUrlOrCode, outputFile, db_manager, custom_option=None):
    # Use custom_option in scraping logic
    if custom_option:
        # ... custom behavior
```

### 3. Update GUI (Optional)

If you want the option exposed in the batch upload dialog:

```python
# GUI_Qt/dialogs/BatchUploadDialog.py
# Add checkbox/dropdown for your custom option
```

### 4. Update BatchProcessor (Optional)

If your option needs special normalization:

```python
# Utilities/BatchProcessor.py
def add_to_queue(self, ...):
    # Add normalization logic for your option
    custom_option = brand_options.get("custom_option")
    # ... normalize ...
```

### 5. Document Here

Add documentation to this file under "Brand-Specific Options".

---

## Troubleshooting

### Option Not Working

**Check normalization:**
```python
# Add debug logging to BatchProcessor.add_to_queue()
self._log("Brand options after normalization", options=normalized_brand_options)
```

**Check uploader receives option:**
```python
# Add debug logging to your brand uploader
self._log("Received brand_options", options=self.brand_options)
```

### Empty String vs None Confusion

**Problem:** Option is empty string `""` instead of `None`

**Solution:** BatchProcessor normalizes this automatically:
```python
description_name = description_name.strip()
if description_name == "":
    description_name = None
```

### Boolean String Conversion

**Problem:** Checkbox value arrives as `"yes"` string instead of `True`

**Solution:** BatchProcessor normalizes this:
```python
if isinstance(append_disclaimer, str):
    append_disclaimer = append_disclaimer.strip().lower() in ("yes", "true", "1")
```

---

## Complete Example: Batch Upload with Mixed Brands

```python
items = [
    {
        "brand": "PINARELLO",
        "code": "F5-2024",
        "url": "https://pinarello.com/f5",
        "description_name": "Premium Road Bike",
        "frameset_only": False,  # Pinarello-specific
        "append_disclaimer": True,
        "append_order_note": False
    },
    {
        "brand": "TREK",
        "code": "FUEL-EX-9.8",
        "url": "https://trekbikes.com/fuel-ex",
        "description_name": None,  # Scrape from website
        "append_disclaimer": False,
        "append_order_note": True
        # No frameset_only (not applicable to TREK)
    },
    {
        "brand": "RASCAL",
        "code": "KIDS-20",
        "url": "https://rascalbikes.com/kids-20",
        "description_name": "Kids Bike Template",
        "variant_index": None,  # Not implemented in GUI yet
        "append_disclaimer": False,
        "append_order_note": False
    }
]

batch_processor.process_batch(items, master_password=password)
```

---

## References

**Core Implementation Files:**
- [Utilities/BatchProcessor.py](Utilities/BatchProcessor.py) - Option normalization
- [Uploaders/BaseUploader.py](Uploaders/BaseUploader.py) - Universal options
- [Uploaders/Pinarello.py](Uploaders/Pinarello.py) - Pinarello-specific options
- [Uploaders/Rascal.py](Uploaders/Rascal.py) - Rascal-specific options
- [GUI_Qt/screens/BatchUploadScreen.py](GUI_Qt/screens/BatchUploadScreen.py) - GUI layer
- [GUI_Qt/dialogs/BatchUploadDialog.py](GUI_Qt/dialogs/BatchUploadDialog.py) - User interface

**Related Documentation:**
- [Database/SessionManager.py](../Database/SessionManager.py) - Encryption strategies
- [Pimbo workflow](pimbo-workflow.md) - Supported product automation
