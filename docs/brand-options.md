# Brand options reference

These options apply to the standard [Upload](../GUI_Qt/screens/UploadScreen.py) and
[Unified Batch](../GUI_Qt/screens/UnifiedBatchScreen.py) workflows. KROSS and Orbea's
supplier pages use separate stage-selection objects described in
[pimbo-workflow.md](pimbo-workflow.md).

## Supported options

| Option | Applies to | Behavior |
| --- | --- | --- |
| `description_name` | All standard uploaders | Saved template name, or `None` for no selected template. A missing/empty selected template fails preparation before product edits. MagicAI still runs later in the standard workflow. |
| `append_disclaimer` | All standard uploaders | Defaults to `False`. Appends the LT disclaimer to the selected template, or prepares the disclaimer alone when no template is selected. |
| `attribute_values` | All standard uploaders | List of objects with `name` and `value`. Selected values must match existing PIMBO Family fields/options; unmatched values fail preparation. |
| `frameset_only` | Pinarello | Explicit `True` or `False` required. `True` collects frame, fork, seatpost and seat clamp only. There is no URL-based auto-detection. |
| `variant_index` | Rascal | Non-negative, zero-based index. Required when the supplier page lists multiple values for a component; unavailable indices fail. Passed through the uploader and batch processor. |
| `preferred_size` | TREK | Exact supplier size label. Required when specifications differ by size; an unavailable size fails. |

`append_order_note=True` is rejected because order-note upload is not implemented.
The standard GUI has a Pinarello frameset checkbox. Rascal/TREK selection controls
are still pending; ambiguous pages stop safely instead of selecting a variant.

## Normalization and batch forwarding

[ProductDataSafety](../Utilities/ProductDataSafety.py) normalizes options for both
[BaseUploader](../Uploaders/BaseUploader.py) and
[BatchProcessor](../Utilities/BatchProcessor.py). Boolean inputs accept booleans,
`true`/`false`, `yes`/`no`, `1`/`0`, and `taip`/`ne`, ignoring case and surrounding
spaces. Empty values default to `False`; invalid boolean text raises an error.
Description names are trimmed; empty names become `None`.

Batch processor items can carry options at the top level or under `brand_options`.
Top-level values take precedence. Workers preserve the options when forwarding an
item. Unknown keys are carried through for future adapters; they do not imply an
implemented behavior. Only options listed above are supported today.

```python
# Options for constructing a Pinarello uploader in the existing app context:
from Uploaders.Pinarello import Pinarello

uploader = Pinarello(
    driver=driver,
    brand_name="Pinarello",
    product_code=product_code,
    url_or_code=supplier_url,
    db_manager=db,
    brand_options={
        "frameset_only": True,
        "description_name": "Saved frameset template",
        "append_disclaimer": False,
    },
)
```

## Data and review rules

Every run owns separate specification files. Missing, malformed, empty or conflicting
source data fails preparation. Scraper errors propagate; old files are never a
fallback. Basso/Lee Cougan require unlocked supplier credentials.

The standard workflow prepares changes for manual PIMBO review and Save. A selected
stage that fails cannot produce a successful preparation. An unsupported standard
image stage fails explicitly; disable image upload or use the applicable supplier
workflow. Stop preserves unsaved partial changes and does not claim they were
discarded.

KROSS/Orbea supplier workflows block automatic saving when selected stages are
missing or fail. A failure after a first successful save remains a failed result;
inspect its completed stages and warnings before retrying.

When adding an option, implement it in the relevant adapter, add validation here,
and extend [product safety regressions](../tests/test_product_data_safety.py).
