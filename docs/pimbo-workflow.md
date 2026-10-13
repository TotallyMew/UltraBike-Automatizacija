# Pimbo workflow

Photo, Geometry and Size Table replacement use the same gallery removal engine:
click the gallery's remove control, accept its known confirmation, wait for the
attachment to disappear, and reread the remaining React controls. Geometry and
Size Table batches reset the hidden input's native value before sending files;
Firefox's Element Clear requires a visible input and fails on the live hidden
controls. The reset never changes display styles or other upload groups.

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

The **Automation** page groups source and data choices, product selection, and
Pimbo updates. **Choose Pimbo products** opens the scan filters; **More filters**
contains optional query settings. The optional catalogue stays with the source
controls. Extra tools contains one image-download form, description extraction,
and Excel sorting. Collection progress appears during a job; the report and
detailed logs can be expanded when needed.

Use **Scan Pimbo** to start a fresh scan of the filtered
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
Use **Resume interrupted run** for the loaded interrupted collection, or choose
an explicit saved run folder. It restores that run's saved scope, filters and
download choices; it never silently switches to a newer collection. Once the Pimbo scan is complete, pending Orbea website lookup and
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
Geometry includes every published setting combination. OCCAM LT M10 exports
six labelled images for Flipchip Low/High × Head Angle Neutral/Slack/Steep,
each containing the S/M/L/XL columns. Frame-size dropdowns remain supported.
The exporter checks refreshed metrics and native selected values rather than
stale decorative dropdown labels; missing or failed combinations stay retryable.
Earlier geometry captures are outdated and refresh on the next selected download.
Successful table refreshes remove obsolete generated table filenames from each
selected product's `tables/` folder after verifying the complete new set. Shared
cached originals and other products are retained. Failed refreshes keep the
previous files and block table upload until the download is complete. The uploader
uses the latest successful file manifest, so leftover files from an earlier app
version or a locked file cannot join the upload. Older packages without a table
manifest use only the main geometry image; refresh tables to collect their full
variant set.
Use **Download selected** with one of three modes:

- **Missing or failed data** collects missing, failed or outdated selected stages
  and retains completed files. Exhausted automatic retries get a fresh attempt;
  confirmed unavailable data stays terminal.
- **Refresh selected data** recollects the chosen stages for checked, visible
  products, including successful or unavailable stages.
- **Photos missing in Pimbo** uses photos only for checked products whose scan
  confirmed an empty gallery. It can find missing supplier links by code.

Choose photos, descriptions, specifications and/or tables for the first two modes.
The eligible count appears before starting. Empty or invalid selections do not
start a collection. Downloads can include products with incomplete local packages
and products from multiple saved runs. **Resume interrupted run** restores the
saved download scope and stages without resetting work completed before Stop.

Use **Load products → Excel** to load a report or product-code sheet. A report
reconnects to its saved collection when available. Choose the download stages and
use **Download selected** to collect data from saved Orbea links without another
Pimbo scan. **Load products → Saved folder** loads an earlier run or a folder of
runs; **Reload current source** reloads exactly the displayed source. The source
path stays visible in the product list.
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
ready to resume; use **Resume interrupted run** to retry. The Pimbo
browser and its login are separate from this Orbea session.
Collection reads Pimbo and saves local files; it does not upload or save product
changes to Pimbo.

Scanned products appear automatically in **Review and select products**. Choose
the rows and the steps in **Update Pimbo**, then press **Upload selected**. Product
actions use checked, visible rows; model filtering keeps hidden checks stored.

To find products with no uploaded photos, use **Load products → Excel** in the product list. A saved Orbea report or any `.xlsx` sheet with a **Variant SKU**, **SKU**,
**Product Code** or **Code** column is supported; Orbea links are optional. Log in
to Pimbo, select the codes to check, and press **Scan Pimbo photos**. The scan
verifies each variant code and reads only its product **Images** gallery. Size
tables and geometry are excluded. **No photos** means zero attached product
images; placeholders and unreadable attached images still count as attachments.
Failed inspection is **Scan error**, and an absent SKU is **Not found**.
Completed checks survive Stop and appear in the **Pimbo Photos** sheet of the
run Excel. The source Excel is kept.

Use **Selection → Add by status → No photos**, then **Download selected** in
**Photos missing in Pimbo** mode. Status selection is additive; only checked bikes
with confirmed empty galleries are eligible for that mode. Downloads retain usable
local photos and use the products' saved collections. Then choose **Upload selected**
with **Upload product photos** and **Arrange photos: side → front → back** enabled.
Loading an Excel preserves the existing upload-step choices. Pimbo's photo status
changes to **Has photos** only after the uploader confirms product attachment.
The scan also works on saved collections loaded from their run folders.

The **Product photos** step removes every existing product-gallery photo,
including Coming Soon placeholders, then uploads the downloaded replacements.
The gallery is cleared once before the first batch, so subsequent batches retain
the new uploads. Missing usable downloads fail the step without removing any
existing photos. Runs skipped by the previous existing-photo rule are eligible
for retry and flagged in exports. Photos go to Product photos,
the CM size guide to Size tables, and the full geometry plus its size and setting variants to
Geometry.

Orbea **Geometry** and **Size Tables** uploads replace their existing attachments after
validating all replacement files. The old files remain in the media library.
Identical copies of the main geometry PNG are uploaded once. Missing or invalid
replacement files leave the existing geometry untouched; failed removal or
incomplete uploads block automatic Save. If Pimbo saves attachments immediately
and leaves the main Save button disabled, the app reloads the product and verifies
the expected table URLs before reporting `saved_automatically` and completing
the Save step. Older `no_changes` records with changed table fields remain
retryable because their persistence was not verified. After Save, the app reloads the product
and verifies the complete replacement URL lists for both galleries. Each table
gallery is handled separately from product photos. Selecting either table upload
automatically enables **Save**; it cannot be unchecked while a table upload is
selected. Missing selected tables or failed uploads block Save and remain retryable.

The saved Features description is pasted before description MagicAI;
family **Dviračiai**, brand **Orbea**, category MagicAI, and translations follow.
After the first verified Save, only Modelis, Spalva, and sorted actual Pimbo variant
frame sizes are filled directly. MagicAI receives the saved Orbea component text
with its original labels and fills the component specifications,
then a second verified Save completes the product. Each step can be selected
independently. Photos-only runs can update multiple products without Save because
Pimbo stores photo attachments immediately. Each batch waits for media upload and
product attachment to finish and confirms the expected gallery count before
continuing. Runs that change form fields without Save target one product for
manual review. Geometry and size-table uploads always save automatically after
the selected first-phase steps complete, before moving to the next product.

Use **Selection → Add by status** to add matching Failed, No changes needed,
Saved, Ready for review, Blocked, Not uploaded yet, With warnings, or photo-scan
statuses to the current visible selection. Other checked products stay checked.
**Clear visible** clears only shown rows; **Select visible** checks them. Incomplete
checkpoint rows can be selected for downloads before an upload package exists.

**Arrange photos: side → front → back** can run by itself on multiple products
without Save. Keep each product's original collected photos; the app matches their
filenames or content hashes to the existing Pimbo images, retains additional
photos, and confirms the saved server order before continuing. New uploads with
all three views receive this order automatically. Missing or ambiguous matches
are reported as failures without changing the gallery.

During uploads, the product table and logs remain scrollable. Activity, History,
Earnings, Spotify, and Info can be viewed while a saved or photos-only upload runs;
return to Orbea to follow its progress. The browser remains reserved by the run.

Source specifications are saved as `specifications.txt`, read from structured
product data or the **Standard configuration** dialog. Its complete component
articles are read even when values are plain text after a heading. Configurator
menus, upgrade prices, and summary choices are excluded. Repeated published
front/rear tyre entries are preserved together. Older incomplete specification
captures must be recollected before specification uploads. **Download selected**
in **Missing or failed data** mode refreshes outdated captures as well as failures.
Products whose Features data is explicitly absent are marked **not available**.
Their description paste and description MagicAI stages are skipped, keeping
existing Pimbo copy and allowing the other selected steps to complete. A present
Features dialog that fails to load remains a retryable collection error.
The full Pimbo model name through its year is pre-filled, including the Orbea
brand, for example `Orbea RISE LT M30 420W 2027`. Colour is taken from the rest
of that name: `Caramel C. View (Matt)- Titan Gold (Gloss)` becomes
`Caramel C. View - Titan Gold`. All Matt/Matte/Gloss/Glossy finish labels are
removed. For names written as `model/year / colour / category (wheel size)`,
only the colour segment is used for photo matching and Spalva. For example,
`DENNA M30 2027 / Nickel (Matt) - Carbon Raw (Gloss) / elektrinis gravel dviratis (28")`
matches Orbea's Nickel colour; its category suffix is excluded. A `Custom`
colour leaves Spalva for manual entry. Wheel size and
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
Successful saved uploads remain unselected when files are reloaded.
Earlier photo results marked No changes after counting submitted files, without
confirming attachment, remain eligible for retry and are flagged in exports. Use **Upload selected** in **Retry unfinished steps** mode to filter checked,
visible rows to unfinished products and resume only missing steps. It never checks
additional products. A verified first-phase save is retained, so a later specification failure
retries the name/colour/size and component AI steps without repeating saved tables,
descriptions, category changes, or translations. Unsaved review changes are never
counted as a saved checkpoint. Confirmed unpublished tables are skipped; missing
files for published tables and collection errors still block their upload.

Product descriptions open the **Features** button linked to
`feature-modules-dialog`, regardless of the website language. The extractor
saves the introduction and all feature cards, including off-screen carousel
cards, without dialog buttons or slider navigation. The standalone descriptions
tool uses the same extraction; older model pages retain their expanded-copy
fallback. **Missing or failed data** also refreshes descriptions saved with the older
short-summary extractor.

Pimbo's page number can update before its table finishes loading. The scanner
waits for the new rows to settle and refreshes the page limit while scanning.
If a run fails, any saved partial report remains available through **Open Excel**
and **Open folder**. Use **Resume interrupted run** to continue a compatible interrupted run.

Use **Product code starts with** to limit the collection to product codes
beginning with a letter or a longer prefix, such as `U` or `U107`. Matching uses
the product code shown in the Pimbo list and ignores letter case. Leave the
field empty to include all codes. Products outside the prefix are skipped
before opening their details and are omitted from the results. The prefix is
saved with the other Orbea filters; resuming requires the same prefix.

## Orbea model copying

Open **Model copying** on the Orbea screen and choose your existing
`orbea_matches.xlsx`, the same workbook used for gathering and uploading data.
In each group's **Source bike** dropdown, choose the bike you have manually
prepared and saved in Pimbo. The dropdown shows SKUs and names from your Excel.
The group becomes checked automatically; uncheck groups you want to leave for
later. **Read sources** reads only checked groups. Source choices are remembered
in the separate checkpoint beside Excel; choosing a different source requires
reading that group's data again. Your Excel file is unchanged by app selections.
Existing `Šaltinis` / `TAIP` Excel marks also load as source choices, so either
method works. An app choice takes precedence for that group. **Read sources** reads
Pimbo's LT name, selected categories, populated attributes, four shared specs,
and the complete description HTML. Review the ready groups and choose
**Copy and save**. Source names must contain `model year / colour / bicycle type`.

Each target keeps its own colour in its name. Specification `Spalva` always
remains unchanged. The **Orbea colour → Spalva attribute** panel contains the
70 supplied paint names with the user's assigned attribute values. Enter only
existing Pimbo dropdown labels; separate multiple selections with `;`. Assignments
are remembered in app settings. Paint matching normalises spacing around
dashes, C. View spelling and Glossy/Matte aliases, and matches the complete paint
combination. Finish labels distinguish assignments such as Frozen Concrete (Gloss)
→ Mėlyna and Frozen Concrete (Matt) → Pilka. Missing or different finish labels
match only when all configured finishes have the same assignment; ambiguous
names retain their existing attribute. Conflicting
assignments for equivalent paint names block copying. Unassigned or unknown paints
keep their current attribute and are noted in the log. Configured choices use the
attribute's existing dropdown and are verified before and after Save. Source-bike
colour attributes are not copied. Copying overwrites categories and populated shared values, leaves
empty source fields alone, and derives `Lako užbaigimas` from the target colour.
Mixed finishes preserve their order; an unknown finish clears that specification.
The workflow translates LT to EN/LV/EE with overwrite, saves Draft targets, and
reloads them to verify the copied values and translations. A dropdown must open
before attribute searching; missing options block saving that product.
Category replacement clicks the selected chips' × controls and chooses exact
paths from the category search list. Attribute replacement uses each field's
own dropdown, waits for React's replacement input and checks retained values.
Description writing opens HugeRTE's **Source Code** dialog, enters the complete
HTML and clicks its **Save** button; it verifies the full formatted HTML before
translation or the separate product Save.

Progress and templates are stored separately beside Excel in
`<workbook-name>_model_copy/model-copy-checkpoint.json`. **Continue** skips
confirmed targets; **Retry failures** retries only failed targets in checked
groups. A new or changed colour assignment makes the relevant previously saved
target eligible again; unchanged assignments keep confirmed results. The colour
mapping fingerprint and expected attribute values are stored with each result,
and the Excel report includes the target paint and assigned attribute values.
**Stop after current product** finishes the current save and leaves the
rest pending. A source version change requires reading sources again. Export
results to a separate Excel file with **Export results**. Excel sorting preserves
the optional `Šaltinis` marks and their corresponding SKUs.

## Safe operation

- Let the active job finish or cancel it before starting another browser job.
- Keep Pimbo open on the page requested by the workflow.
- Do not edit a product manually while an automated step is saving it.
- Use the Activity page and processing history to review results and diagnostics.
