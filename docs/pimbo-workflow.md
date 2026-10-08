# Pimbo workflow

UltraBike Automatizacija manages product data through the authenticated Pimbo
web application. It uses a Selenium browser owned by the main window; only one
long-running workflow may control that shared browser at a time.

## Sign in

Save the administrator credentials on the Account page, then sign in. The app
opens Pimbo and retains an encrypted local session for the configured lifetime.
Brand credentials are stored separately and are only used by their matching
upload workflow.

## Product automation

Bulk uploads run through dedicated **Orbea** and **KROSS** screens. Choose the
products and stages in the relevant supplier workflow, then review its saved
results before retrying. Pimbo MagicAI titles, source descriptions, category
suggestions, translations, and specifications remain available where supported.
Title and description MagicAI template names are configurable in Settings.

The single Upload, Unified Batch, description-template editor, Folder Creator,
and old Analytics screens have been retired. Existing history, stored templates,
and translation dictionaries are preserved. Future bulk workflows belong in
separate product or supplier screens.

**Product lookup and export** brings names by code, code export, and name export
together as three modes. **History** opens the detailed searchable records
directly and can export historical upload results to Excel. **Earnings** retains
its earnings analysis, goals, and manually recorded work.

## KROSS

Collect KROSS source data or open a saved collection, select products and upload
stages, then run the selected updates. The workflow records saved results and
supports Excel export. Keep translation dictionaries available for KROSS source
processing; the retired description-template editor does not affect supplier
description collection or Pimbo MagicAI.

## Orbea

The **Automation** page follows three numbered steps: **1. Get products from Pimbo**,
**2. Choose products**, and **3. Update Pimbo**. The code prefix, Draft/status and
stock filters stay visible. **More filters and optional catalogue** expands the
remaining filters and Excel catalogue input. Standalone image, description, and
Excel tools live under **Extra tools**. Collection progress appears while running;
the report and detailed logs can be expanded when needed.

Use **Scan Pimbo and collect Orbea data** to start a fresh scan of the filtered
Pimbo product list. Each page is read together: the full title comes from the
row's title attribute and a variant code comes from its visible code label.
For example, `U34007IR +3` saves `U34007IR`; `+3` is a count of additional
variants, not part of the code. Product pages and Variants tabs are never opened
during scanning. Any listed variant identifies the model for TTCC lookup, so
in-stock variant selection is unnecessary. List stock remains aggregate stock;
individual variant stock is not inferred.

Repeated rows without a product link are recognised by their exposed SKU across
pages and resume. Different variant SKUs remain separate Pimbo targets and share
one model URL lookup. Actual product links/IDs are retained when present; rows
without them leave those fields empty. Upload resolves the saved full SKU in
Pimbo and verifies the target before editing. Rows with missing or malformed
codes stay for review without falling back to a product-page visit.
URL lookup always uses the model reference with a `TTCC` ending (for example,
`U10707SV` becomes `U107TTCC`). Full variant codes and product names are never
search terms or matching criteria. The optional Excel catalogue can help with
bicycle filtering; its links do not override website code confirmation.

Orbea's own location selector supplies every advertised country/language site,
including International. English sites are tried first, with other languages
retained as fallbacks. Each search reads the code and URL from the same popup
row and selects the first **exact code match**. Fuzzy or unrelated results are
ignored without opening their product pages. Once a code is found, remaining
regions are skipped. An unresolved code is searched in every discovered site;
a failed regional search stays retryable rather than being called unmatched.
One lookup is shared by all Pimbo SKUs for that model code, including verified
links and completed "not found" results from a resumed scan. Retryable regional
errors remain eligible for another attempt. Logs and progress label reused
results explicitly, rather than showing another search for each colour/size;
the checkpoint records the TTCC query and whether a row used a fresh, shared,
or previously saved result.

The full Pimbo scan is saved first. Then **all URLs are gathered and saved**,
with no product-page or image collection during lookup. Selected downloads
start only after the URL stage finishes and proceed through the matched URLs
systematically. Product pages are checked by code when opened for collection;
regional or renamed product titles do not reject a matching code. The Excel is
saved before website lookup, after URL gathering, and after each collection.
The main button always reads the current Pimbo products into a new run folder.
Use **Resume interrupted collection** to reopen the latest unfinished run in the
selected output folder. Its saved filters and download choices are restored
automatically. Once the Pimbo scan is complete, pending Orbea website lookup and
downloads do not require a Pimbo connection or the original catalogue workbook.
An unfinished Pimbo scan still requires login. The text below Resume explains
which run will continue or why the button is unavailable.

Select product photos, geometry and CM size tables, source descriptions, and
source specifications. Each product is saved under `products/<SKU>/` in the
dated run folder, with `orbea-product.json`, `description.html`,
`specifications.txt`, `photos/`, and `tables/` as selected. The workbook's
**Collected Products** sheet links to these folders and shows each download's
status. Missing source data is reported; access checks and download failures
keep the run partial and retryable. Resume skips saved successful stages.
Use **Retry matched downloads** to refresh the saved download choices for every
code-matched product, including already successful downloads and products marked
as unavailable. This also works for completed runs, reuses the saved URLs, and
does not scan Pimbo or search unmatched products. **Retry failed downloads**
keeps successful current captures and retries failed, missing, or outdated data.
If the matched retry is stopped, **Resume interrupted collection** continues
the downloads that remain pending.
Untick **Product photos** to collect the other selected data without downloading
bike photos. Resume restores the saved run's download choices.
Use **Open saved collection** to choose a finished Orbea report. The app reconnects
to its original collection and shows how many products already have each item.
Change the download checkboxes, then press **Download selected missing items** to
add photos, descriptions, specifications, or tables using the saved Orbea links.
Existing successful files and upload results are kept. No Pimbo login, scan, or
regional model search is needed. Interrupted downloads resume with these choices.
A copied report can reconnect through its saved collection folder. If only the
Excel remains, its Matches sheet supplies the product codes and links for a new
download collection; the original Excel is kept. Original local files and upload
history remain available when the original collection folder is present.
Identical photos share disk storage across SKUs and fresh runs, with reusable
images in `.orbea-assets/` under the output folder. Product folders retain their
normal image paths for uploads. Tables share storage with the run's originals.
On drives without hard-link support, collection falls back to separate copies
and reports this in the log.
Orbea opens in a visible, separate browser with a dedicated session reused on
later runs. If a website security check appears, complete it in that browser.
Collection waits up to five minutes and continues automatically when the shop
opens. **Stop** saves the scan, completed downloads and partial Excel immediately.
If verification remains unresolved, the screen and Activity show partial work
ready to resume; use **Resume interrupted collection** to retry. The Pimbo
browser and its login are separate from this Orbea session.
Collection reads Pimbo and saves local files; it does not upload or save product
changes to Pimbo.

Collected products appear automatically in **2. Choose products** for the same
editing sequence as KROSS. Use **Load saved products** to reopen saved files, or
**Choose another folder** to load an earlier run or a single product folder. Select
products, then choose the steps in **3. Update Pimbo** and press **Upload to Pimbo**.
Photos go to Product photos,
the CM size guide to Size tables, and the full geometry plus its size variants to
Geometry. The saved Features description is pasted before description MagicAI;
family **Dviračiai**, brand **Orbea**, category MagicAI, and translations follow.
After the first verified Save, only Modelis, Spalva, and sorted actual Pimbo variant
frame sizes are filled directly. MagicAI receives the saved Orbea component text
with its original labels and fills the component specifications,
then a second verified Save completes the product. Each step can be selected
independently; without Save, only one product can be run for manual review.

Source specifications are saved as `specifications.txt`, read from structured
product data or the **Standard configuration** dialog. Its complete component
articles are read even when values are plain text after a heading. Configurator
menus, upgrade prices, and summary choices are excluded. Repeated published
front/rear tyre entries are preserved together. Older incomplete specification
captures must be recollected before specification uploads; **Retry failed**
refreshes the old capture version as well as failed downloads.
Products whose Features data is explicitly absent are marked **not available**.
Their description paste and description MagicAI stages are skipped, keeping
existing Pimbo copy and allowing the other selected steps to complete. A present
Features dialog that fails to load remains a retryable collection error.
The full Pimbo model name through its year is pre-filled, including the Orbea
brand, for example `Orbea RISE LT M30 420W 2027`. Colour is taken from the rest
of that name: `Caramel C. View (Matt)- Titan Gold (Gloss)` becomes
`Caramel C. View - Titan Gold`. All Matt/Matte/Gloss/Glossy finish labels are
removed. A `Custom` colour leaves Spalva for manual entry. Wheel size and
Lako užbaigimas are always left for manual entry, including during MagicAI;
existing manual values are preserved. Actual Pimbo variant frame sizes are
deduplicated and sorted from smallest to largest, for both S/M/L sizes and
numeric sizes such as 45/51/63. Component values are handled by MagicAI using
Pimbo's actual fields; the app does not map component labels to assumed fields.
The model/colour/size step can run without component data. Component MagicAI
requires the saved source and never receives a name-only prompt.

Before any edit, the workflow verifies the representative SKU in Pimbo Variants
and the saved package's product owner, then checks Draft status. Required-stage
failures block automatic Save. Results and completed steps are saved in
`orbea-upload-result.json`; the screen and Activity show failures and warnings.
**Stop after current product** finishes the active product and leaves remaining
products for a later run. Before a multi-product upload starts, existing unsaved
Pimbo edits block the batch without changing any product's saved retry progress.
The message names the open product. Failed batches reset only the verified failed
product; a fresh reload with the same product ID permits returning to Products
even if Pimbo enables Save from defaults. A changed product ID still stops the
batch. Stop messages include the product failure and the recovery error.
Successful saved uploads remain unselected when files are reloaded. Use **Retry
failed and unprocessed uploads** to skip successful bikes and resume only missing
steps. A verified first-phase save is retained, so a later specification failure
retries the name/colour/size and component AI steps without repeating saved tables,
descriptions, category changes, or translations. Unsaved review changes are never
counted as a saved checkpoint. Confirmed unpublished tables are skipped; missing
files for published tables and collection errors still block their upload.

Product descriptions open the **Features** button linked to
`feature-modules-dialog`, regardless of the website language. The extractor
saves the introduction and all feature cards, including off-screen carousel
cards, without dialog buttons or slider navigation. The standalone descriptions
tool uses the same extraction; older model pages retain their expanded-copy
fallback. **Retry failed** also refreshes descriptions saved with the older
short-summary extractor.

Pimbo's page number can update before its table finishes loading. The scanner
waits for the new rows to settle and refreshes the page limit while scanning.
If a run fails, any saved partial report remains available through **Open Excel**
and **Open folder**. Use **Resume interrupted collection** to continue a compatible interrupted run.

Use **Product code starts with** to limit the collection to product codes
beginning with a letter or a longer prefix, such as `U` or `U107`. Matching uses
the product code shown in the Pimbo list and ignores letter case. Leave the
field empty to include all codes. Products outside the prefix are skipped
before opening their details and are omitted from the results. The prefix is
saved with the other Orbea filters; resuming requires the same prefix.

## Safe operation

- Let the active job finish or cancel it before starting another browser job.
- Keep Pimbo open on the page requested by the workflow.
- Do not edit a product manually while an automated step is saving it.
- Use the Activity page and processing history to review results and diagnostics.
