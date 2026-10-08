# Known issues and technical debt backlog

Reviewed: **8 October 2026**. All items are open unless their checkbox is marked.

This records the findings from the code assessment, including the current uncommitted supplier workflow changes. It is a backlog of known problems and follow-up investigations, not a claim that every possible bug has been discovered. Line numbers describe the review snapshot and may move.

The Single Upload, Unified Batch, Descriptions, Folder Creator, and old Analytics
screens were retired on 8 October 2026. References to those UI files below are
historical review evidence. Supplier adapters and translation code remain for
future dedicated bulk workflows. TD-022 and TD-023 were retired with their UI;
shared database, browser, and supplier-library debt remains relevant.

## How to use this backlog

- **P1:** Fix before relying on the affected workflow or expanding it. Includes data accuracy, broken functionality, and concurrency risks.
- **P2:** Address in planned maintenance and before substantial related feature work.
- **P3:** Lower urgency capability, documentation, or tooling improvements.
- **Reproduced defect:** Verified with an isolated offline reproduction; no live Pimbo upload was performed.
- **Code-confirmed defect:** The incorrect behavior is directly visible in the implementation; a complete user workflow was not replayed.
- **Risk:** A hazardous implementation is present, but the resulting user incident has not been reproduced.
- **Debt:** A structural obstacle to maintenance or extension.
- **Observed failure / Investigation:** A test or development workflow failed; the cause still needs isolation.

Keep the ID when fixing an item. Mark it complete only after its acceptance condition is satisfied, and add a commit or PR reference and the validation performed. Some items overlap intentionally: repairing a symptom does not automatically complete the broader design work.

## Broken functionality and data accuracy

- [x] **TD-001 — P1 · Reproduced defect: failed scraping can reuse a previous product's specifications.**

  **Evidence:** [TranslationManager](../Managers/TranslationManager.py#L37) ignores the scraper return value, then reads a persistent brand file. [KROSS](../Scrapers/KROSSScraper.py#L102), Pinarello, Factor, Rondo, Rascal, Octane, TREK, Basso, and Lee Cougan return error strings for at least some failures. An offline KROSS connection failure still loaded a seeded previous product and invoked translation.

  **Done when:** Every scraper has an explicit success/failure contract. Failure stops preparation before Pimbo changes; only output produced for the current product/run is accepted. Cover both an existing stale file and a missing file.

  **Fixed (7 October 2026):** Fresh output is required; failures propagate and previous files are removed. Covered by stale/missing-output and uploader-stage regressions. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [x] **TD-002 — P1 · Reproduced defect: five scraper call signatures are incompatible with their uploaders.**

  **Evidence:** [TranslationManager](../Managers/TranslationManager.py#L40) always supplies `bicycleUrlOrCode`, `outputFile`, and `db_manager`. TREK, Rondo, Rascal, and Octane accept `url`; Lee Cougan accepts `target_code`; TREK also lacks `db_manager`. All five calls raised `TypeError` offline before scraping.

  **Done when:** Each offered brand works through its actual uploader-to-scraper call path with mocked supplier responses. Verify TREK, Rondo, Rascal, Octane, and Lee Cougan individually; give adapters one documented interface.

  **Fixed (7 October 2026):** The translation boundary binds the actual scraper signature and supports all nine brand adapters. Contract regressions cover every uploader. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [x] **TD-003 — P1 · Reproduced defect: TREK calls removed translation methods.**

  **Evidence:** [TREKScraper.py:40–41](../Scrapers/TREKScraper.py#L40) calls instance methods `load_translations` and `load_value_translations` that do not exist on `TranslationHandler`. Calling the scraper with the correct positional arguments exposed the next `AttributeError`.

  **Done when:** TREK uses the supported translation interface and injected database. Its complete offline scraper test reaches parsing and produces validated output after TD-002 is repaired.

  **Fixed (7 October 2026):** TREK uses the supported database translation API; real HTML parsing reaches validated output in offline tests. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [x] **TD-004 — P1 · Code-confirmed defect: TREK references missing translation files and depends on the working directory.**

  **Evidence:** [TREKScraper.py:40–41](../Scrapers/TREKScraper.py#L40) references `vertimasDetalesEN-LT.txt` and `vertimasSavybesEN-LT.txt`; bundled names contain `ENG-LT`. Paths are relative to the process working directory.

  **Done when:** Use database translations or the application's resource resolver with actual resource names. Verify from a different working directory and in the packaged resource layout.

  **Fixed (7 October 2026):** TREK no longer reads legacy translation resources. An injected-database test runs from a different working directory. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [x] **TD-005 — P1 · Reproduced defect: standard KROSS image upload calls a nonexistent method.**

  **Evidence:** [BaseUploader.py:405](../Uploaders/BaseUploader.py#L405) calls `download_kross_images`; [ImageHandler.py:26](../Utilities/ImageHandler.py#L26) only defines `Fdownload_kross_images`. An offline upload call emitted `UPLOAD_IMAGE_FAILED`, never called the editor image upload, and returned without raising.

  **Done when:** Correct the interface and verify the complete standard KROSS image stage with mocked downloads and editor calls, including an empty download result.

  **Fixed (7 October 2026):** The downloader/editor method contract is repaired. Verified current images and a complete standard image-stage regression replace stale directory enumeration. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [x] **TD-006 — P1 · Reproduced defect: selected stage failures disappear from the preparation result.**

  **Evidence:** [BaseUploader.uploadImages](../Uploaders/BaseUploader.py#L396) catches errors and continues without adding them to `_preparation_warnings`. TD-005 produced an empty warnings list. Some description failures also only emit notifications. Unsupported standard brand image stages only emit a warning.

  **Done when:** A selected stage reports completed, skipped, unavailable, or failed in the returned result and persisted history. Required failures block success; optional failures remain visible in the final review summary.

  **Fixed (7 October 2026):** Required description, image, attribute, specification and AI failures produce failed results. Shared supplier workflows also block Save on selected-stage failures. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [x] **TD-007 — P1 · Reproduced defect: missing specification files become empty successful input.**

  **Evidence:** [FileHandler.read_translated_file](../Utilities/FileHandler.py#L9) creates a missing file and returns an empty list. Malformed lines are notified and skipped while partial data is returned; other read errors can also fall through to a result.

  **Done when:** Missing, unreadable, and malformed required sources produce a structured failure. An intentionally empty source is explicit and cannot be confused with an unavailable source.

  **Fixed (7 October 2026):** Missing, empty, malformed and conflicting sources raise; no empty file is created as fallback. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [x] **TD-008 — P1 · Reproduced defect: batch string booleans are converted incorrectly.**

  **Evidence:** [BatchProcessor.process_batch](../Utilities/BatchProcessor.py#L277) applies `bool(...)` before queue normalization. Offline input `frameset_only="false"` and `append_disclaimer="false"` reached the uploader as `True`.

  **Done when:** Single and batch entry points share one normalization function. Test booleans, `true`/`false`, `yes`/`no`, `1`/`0`, whitespace, empty values, and invalid values.

  **Fixed (7 October 2026):** Single and batch upload share ProductDataSafety normalization, including true/false strings, whitespace, empty inputs and invalid values. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [ ] **TD-009 — P2 · Reproduced defect: batch processing drops brand options.**

  **Evidence:** [BatchProcessor.process_batch](../Utilities/BatchProcessor.py#L277) rebuilds a fixed option dictionary even though `add_to_queue` preserves arbitrary options. Offline input lost `variant_index`, `append_order_note`, and a custom option.

  **Done when:** Define supported options explicitly, preserve them across the whole call chain, and reject unsupported options clearly. A supported new option should not require edits in every intermediate layer.

  **Progress / remaining work (7 October 2026):** Batch and worker forwarding preserve supplier options, and unsupported order-note requests fail explicitly. Unknown option keys are still carried for future adapters; a fully typed/strict option schema remains pending. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [x] **TD-010 — P2 · Code-confirmed defect: cancelled batches report all queued items as completed.**

  **Evidence:** [BatchProcessor.start_batch](../Utilities/BatchProcessor.py#L232) sets `current_index = len(self.queue)` after a stop breaks the loop, despite the documented meaning being completed count.

  **Done when:** Progress equals actual processed items; the summary distinguishes processed, remaining, failed, blocked, and cancelled items. Stopping after the first item in a longer batch must not report 100% completion.

  **Fixed (7 October 2026):** Cancelled batch summaries retain actual processed/remaining counts; a three-item regression stopped after item one. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [x] **TD-011 — P2 · Reproduced defect: the Le Grand uploader alias never matches.**

  **Evidence:** [uploaderFactory.py](../uploaderFactory.py#L11) removes spaces from input but keeps the dictionary key `le grand`. `getUploaderClass("Le Grand")` returned `None` offline.

  **Done when:** Normalize registry keys and incoming names consistently. Test all aliases and whitespace/case variants; handle an unknown brand explicitly instead of trying to call `None`.

  **Fixed (7 October 2026):** Registry aliases normalize consistently; four Le Grand spelling/case/spacing variants are covered. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [ ] **TD-012 — P3 · Capability gap: Rascal variant selection is ignored.**

  **Evidence:** [Uploaders/Rascal.py:9](../Uploaders/Rascal.py#L9) hardcodes `variant_index = None` instead of consuming a supplied option. The GUI does not offer selection. Existing documentation describes the limitation; it remains incomplete functionality.

  **Done when:** Either implement a reviewed variant selection path through uploader, batch, and scraper, or make the supported limitation explicit and reject unsupported variant options.

  **Progress / remaining work (7 October 2026):** Rascal now consumes and forwards variant_index, and ambiguous/out-of-range variants fail safely. GUI selection controls remain pending; TREK preferred_size has the same UI limitation. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [x] **TD-013 — P2 · Code-confirmed defect: credential preflight errors are swallowed.**

  **Evidence:** [UploadScreen.py:955–977](../GUI_Qt/screens/UploadScreen.py#L955) catches all errors while checking external credentials and unlocking the master password, then proceeds. Basso and Lee Cougan uploaders also silently convert credential-loading errors into absent credentials.

  **Done when:** Distinguish missing credentials, cancelled unlock, decrypt failure, and unexpected failure. Each stops or follows an explicit recovery path and retains diagnostics without logging secrets.

  **Fixed (7 October 2026):** Credential/decryption errors propagate and stop scraping. Basso and Lee Cougan regressions verify no scraper call after unlock failure. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

## Concurrency, cancellation, and lifecycle

- [x] **TD-014 — P1 · Risk: parallel same-brand uploads share translation files.**

  **Evidence:** [TranslationManager.py:17–18](../Managers/TranslationManager.py#L17) uses one LT and EN filename per brand. [ParallelBatchUploadWorker](../GUI_Qt/workers/batch_workers.py#L364) runs multiple uploader threads. Those threads can overwrite or read each other's source and translated files.

  **Done when:** Each product/run owns separate output or returns in-memory product data. A controlled two-product, same-brand concurrency test cannot cross-contaminate specifications or AI source text.

  **Fixed (7 October 2026):** Each run owns separate paths. A barrier-controlled, two-thread test verifies same-brand product isolation through scraping and translation. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [ ] **TD-015 — P1 · Risk: shared browser ownership is enforced only in some workflows.**

  **Evidence:** [MainWindow's lease](../GUI_Qt/MainWindow.py#L377) is used by Orbea and Kross, but standard Upload and Unified Batch do not acquire it. `track_worker` only tracks activity; navigation guards do not cover those screens' running workers.

  **Done when:** Every workflow using the authenticated driver acquires one shared ownership mechanism for its whole operation and review phase. Starting a second conflicting workflow is rejected safely; ownership is released on every exit path.

  **Progress / remaining work (7 October 2026):** Standard Upload and Unified Batch now acquire ownership through execution/review; navigation blocks active worker/lease transitions. Other authenticated read-only tools still need explicit leases rather than relying on navigation guards. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [x] **TD-016 — P1 · Code-confirmed defect: standard cancellation can label continuing work as discarded.**

  **Evidence:** [UploadWorker](../GUI_Qt/screens/UploadScreen.py#L81) calls the complete uploader without a cancellation token. Stop is checked during retry waits and after `uploader.run()`, when the result is replaced with `DISCARDED`. Normal upload stages do not check the stop request, and the worker does not actually discard the browser form.

  **Done when:** Stop is observed at safe stage boundaries; no later stages start. Return the actual partial browser state and preserve a review/discard path. Do not claim a discard without verifying it.

  **Fixed (7 October 2026):** Stop reaches the uploader and active batch processors, is checked between stages/items/AI actions, and preserves partial preparation metadata. UploadWorker never substitutes an unverified discard. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [x] **TD-017 — P2 · Risk: an early Orbea stop request can be lost during token replacement.**

  **Evidence:** [OrbeaRunWorker.run](../GUI_Qt/orbea/workers.py#L86) replaces its existing cancellation event with a new token without preserving whether stop was already requested. Photo/table workers carry `_stop_requested` and replay it; the run worker does not. Filter discovery also starts even if already stopped.

  **Done when:** All workers preserve stop requests made before service construction, during construction, and during execution. Use one token per job or propagate the prior cancelled state.

  **Fixed (7 October 2026):** OrbeaRunWorker retains and replays an early stop across token replacement; filter discovery also checks stop before and after service construction. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

  **Follow-up (8 October 2026):** Orbea workers now keep one token for their entire lifetime; token replacement/replay is removed. Startup-race regressions cover collection, description, photos, tables and filter discovery.

- [x] **TD-018 — P1 · Risk: hiding Unified Batch closes browser sessions still in use.**

  **Evidence:** [UnifiedBatchScreen.hideEvent](../GUI_Qt/screens/UnifiedBatchScreen.py#L1015) calls `session_manager.shutdown_all()` on hide, without first confirming its batch workers have stopped using the sessions.

  **Done when:** Navigation away either preserves the running batch or performs a coordinated stop-and-wait before closing drivers. Verify switching screens during a parallel batch and during manual review.

  **Fixed (7 October 2026):** Unified Batch refuses navigation and pool shutdown during running work or dirty review. Shared browser checks include pooled sessions. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [ ] **TD-019 — P1 · Risk: shared SQLite transaction ownership is inconsistent.**

  **Evidence:** [DatabaseManager](../Database/DatabaseManager.py#L17) shares a connection with `check_same_thread=False`. Settings, operations, backups, and some services use `write_lock`; [BaseUploader history writes](../Uploaders/BaseUploader.py#L238), many EarningsManager methods, and GUI writes do not. Parallel batch workers share this database.

  **Done when:** Establish one connection/transaction ownership policy and apply it to every writer. Verify concurrent history, earnings, settings, operation tracking, and backup activity cannot commit or roll back another operation's transaction.

  **Progress / remaining work (7 October 2026):** Product history/cache writes, review decisions, description CRUD/reads and translation queries now use the shared lock. The concurrency regression reproduced a SQLite InterfaceError before translation queries were serialized. Earnings and other writers still need one repository-wide policy. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [ ] **TD-020 — P2 · Risk: browser pool leases do not enforce lifecycle invariants.**

  **Evidence:** [BrowserSessionManager](../Managers/BrowserSessionManager.py#L157) acquires any non-busy session without checking its driver. `release_session` always releases a semaphore permit, including duplicate releases; shutdown/reinitialization does not reset semaphore state. Failed resets can leave a session with `driver=None`.

  **Done when:** Validate session membership, driver health, and ownership; make release idempotent; restore permit counts on lifecycle changes. Test double release, failed reset, shutdown with active leases, and reinitialization without launching real browsers.

  **Progress / remaining work (7 October 2026):** Fixed duplicate release, foreign-session release, null-driver acquisition and semaphore reinitialization. Reset refuses dirty product forms. Health validation and coordinated shutdown with active leases remain broader lifecycle work. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [ ] **TD-021 — P2 · Code-confirmed defect: legacy supplier requests lack timeouts.**

  **Evidence:** [KROSSScraper.py:23](../Scrapers/KROSSScraper.py#L23) and [TREKScraper.py:45](../Scrapers/TREKScraper.py#L45) call `requests.get` without a timeout. A stalled request can prevent cancellation and shutdown from completing promptly.

  **Done when:** Supplier HTTP calls have bounded connect/read timeouts, a defined retry policy, and cancellation checks between requests. Timeout behavior returns a clear failure rather than stale output.

  **Progress / remaining work (7 October 2026):** KROSS/TREK HTTP requests now have timeouts and failures propagate. Stop is observed at uploader boundaries; finer request cancellation/retry policy remains pending. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [x] **TD-022 — P2 · Risk: browser work and waits block the GUI thread.**

  **Evidence:** [UploadScreen._confirm_regular_save](../GUI_Qt/screens/UploadScreen.py#L1153) calls Selenium verification directly from the GUI; [verify_manual_save](../Managers/PimboProductEditor.py#L1939) can perform two waits. [Batch execution](../GUI_Qt/batch/execution.py#L190) synchronously creates and logs in a browser pool before starting its worker.

  **Done when:** Move browser startup/login and save verification into workers with progress, bounded cancellation, and error results. The GUI must remain responsive during slow or failed browser operations.

  **Retired (8 October 2026):** Removed the Single Upload and Unified Batch UI paths that contained this behavior.

- [x] **TD-023 — P2 · Risk: manual save confirmation updates history by latest SKU instead of operation identity.**

  **Evidence:** [UploadScreen.py:1179](../GUI_Qt/screens/UploadScreen.py#L1179) selects the latest `ready_for_review` history row using only `product_code`. The preparation result is not tied to the exact history row being updated.

  **Done when:** Carry the history/operation ID through preparation and save confirmation. Repeated or concurrent runs for the same SKU must update the correct record and earnings association.

  **Progress / remaining work (7 October 2026):** Preparation carries history_id; standard Save and batch review status updates use that exact row and verify its product identity. Batch earning-candidate lookup still queries recent rows by SKU and should carry IDs end to end. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

  **Retired (8 October 2026):** Removed the Single Upload and Unified Batch UI paths that contained this behavior.

## Architecture and extension cost

- [ ] **TD-024 — P2 · Debt: OrbeaScreen combines UI and workflow coordination.**

  **Evidence:** [OrbeaScreen](../GUI_Qt/screens/OrbeaScreen.py#L103) has 3,259 lines and 135 methods. It owns controls, settings, service configuration, workers, reports, resuming, errors, and state transitions. `_update_action_states` alone spans 178 lines.

  **Done when:** Extract coherent panels and an explicit workflow state/controller. Presentation consumes that state; adding a workflow stage does not require duplicating start/stop/busy/retranslate logic across the screen.

  **Progress (8 October 2026):** Descriptions, photos and table-image jobs now have separate QObject controllers and a shared start/cleanup lifecycle. Active-job ownership and input locking are centralized; OrbeaScreen shrank from 3,378 to 2,724 lines in this working-tree snapshot. Layout, translation, settings and collection/resume presentation still need smaller boundaries, so this item remains open. See [Orbea maintenance guide](orbea-maintenance.md).

- [ ] **TD-025 — P2 · Debt: earnings responsibilities are concentrated in two large classes.**

  **Evidence:** [EarningsScreen](../GUI_Qt/screens/EarningsScreen.py#L126) has 2,985 lines; [EarningsManager](../Managers/EarningsManager.py#L87) has 78 methods in a 1,674-line module. Entries, sessions, goals, quests, projections, charts, and presentation interact through these classes.

  **Done when:** Separate entries, sessions, goals, and reporting into focused services/controllers while preserving the existing accounting and no-double-counting behavior. Keep UI formatting outside business rules.

- [ ] **TD-026 — P2 · Debt: MainWindow is an implicit service container and lifecycle coordinator.**

  **Evidence:** [MainWindow](../GUI_Qt/MainWindow.py#L47) has 1,796 lines and 73 methods. Screens access its database, driver, settings, credentials, translations, navigation, worker tracking, and other screens through `self.main`.

  **Done when:** Introduce an explicit application context with narrow dependencies. Keep shell presentation/navigation in the window and move job/browser/session ownership into focused services.

- [ ] **TD-027 — P2 · Debt: settings construction and styling are oversized and repetitive.**

  **Evidence:** [SettingsScreen](../GUI_Qt/screens/SettingsScreen.py#L228) has a 585-line `_init_ui` method in a 1,437-line module. Large theme/retranslation methods recur in other screens, including earnings.

  **Done when:** Extract settings sections and shared field/panel patterns; use common theme and translation helpers. A new setting has one definition for defaults, validation, persistence, and presentation where practical.

- [ ] **TD-028 — P2 · Debt: the shared supplier upload method is a branching monolith.**

  **Evidence:** [SupplierUploadWorkflow.upload_and_save](../tools/supplier_upload.py#L97) spans 434 lines and coordinates source loading, files, specifications, AI, warnings, and two save phases using mutable local flags and nested helpers.

  **Done when:** Represent stage selection, ordering, prerequisites, results, and save boundaries explicitly. Extract independently understandable stages without weakening Draft checks, target verification, or partial-failure handling.

- [ ] **TD-029 — P2 · Debt: supplier workflow interfaces are implicit.**

  **Evidence:** [SupplierUploadWorkflow](../tools/supplier_upload.py#L26) depends on subclass-supplied attributes and methods such as `workflow_options_type`, `upload_result_type`, `public_catalog`, `editor_factory`, and `resolve_match`, with many `Any` inputs and outputs.

  **Done when:** Define a typed supplier adapter contract and validated product/result models. Incomplete adapters fail before beginning a browser operation; adding a brand has a documented small integration surface.

- [ ] **TD-030 — P2 · Debt: Kross service module combines unrelated layers.**

  **Evidence:** [tools/kross_automation/service.py](../tools/kross_automation/service.py) contains 1,858 lines covering models, public catalogue HTTP/parsing, images, Pimbo scanning, browser editing, and orchestration.

  **Done when:** Separate models, catalogue access, Pimbo adapters, and orchestration into modules with clear ownership and one-way dependencies.

- [ ] **TD-031 — P2 · Debt: supplier modules depend on one another for shared infrastructure.**

  **Evidence:** [Kross service](../tools/kross_automation/service.py#L37) imports Pimbo models/client from Orbea; [Orbea upload](../tools/orbea_automation/upload.py#L8) imports Kross's client and workflow options. Shared concepts are housed under supplier-specific packages.

  **Done when:** Move genuinely shared Pimbo/filter/workflow concepts into a neutral package. Kross and Orbea adapters depend on shared infrastructure rather than each other.

- [ ] **TD-032 — P2 · Debt: runtime compatibility adaptation hides interface drift.**

  **Evidence:** [Orbea controller](../GUI_Qt/orbea/controller.py#L10) uses signature inspection, field aliases, mapping/object fallbacks, and `hasattr` for in-repository services and models; the screen repeats aliases and fallback reads.

  **Done when:** Use canonical typed interfaces internally. Keep necessary external/legacy compatibility in explicit boundary adapters with tests and version policy, rather than throughout the UI.

- [ ] **TD-033 — P2 · Debt: business workflows and persistence are coupled to presentation.**

  **Evidence:** [UploadScreen](../GUI_Qt/screens/UploadScreen.py#L1179) performs SQL updates and earnings association; [BaseUploader.run](../Uploaders/BaseUploader.py#L117) combines scraping, translation, Pimbo edits, history, caching, and user notifications.

  **Done when:** Workflows return structured results; repositories own persistence; the GUI owns presentation. Run the same business workflow offline or from a non-GUI caller without needing a screen.

- [ ] **TD-034 — P2 · Debt: adding brands and screens requires updating multiple registries.**

  **Evidence:** Brand names appear in uploaderFactory, UploadScreen, UnifiedBatchScreen, BatchUploadDialog, and database seeds. Screen modules/attributes appear in [routes](../GUI_Qt/routes.py), MainWindow, [shutdown](../GUI_Qt/services/shutdown.py#L8), [import smoke](../tools/smoke_imports_ui.py), and [packaging](../ultrabike.spec).

  **Done when:** Define brand capabilities and screen registration in authoritative registries. Derive dropdowns, factories, shutdown participation, and packaging/import validation where appropriate; validate required registrations automatically.

- [ ] **TD-035 — P2 · Debt: worker lifecycle and cancellation code are duplicated.**

  **Evidence:** [Orbea workers](../GUI_Qt/orbea/workers.py), [Kross workers](../GUI_Qt/kross/workers.py), and [batch workers](../GUI_Qt/workers/batch_workers.py) independently implement stop flags, tokens, service cancellation, signals, exceptions, review waits, and cleanup. TD-017 illustrates divergent behavior.

  **Done when:** Share a small job lifecycle/cancellation contract and common adapters. Retain workflow-specific behavior explicitly and verify startup, stop, partial result, failure, review, and shutdown consistently.

  **Progress (8 October 2026):** Orbea collection, filter, description, photo and table workers share one cancellation handshake and retain one token across service construction. Cancellation reaches an attached service once, including an early stop and a failing cleanup method. Partial results remain workflow-specific. Kross/batch/review lifecycle sharing remains open; the new worker regressions cover Orbea's portion.

- [ ] **TD-036 — P2 · Debt: Pimbo editor and scraper helpers need smaller internal boundaries.**

  **Evidence:** [PimboProductEditor](../Managers/PimboProductEditor.py#L165) is 2,039 lines; [Orbea table downloader](../tools/orbea_table_image_downloader.py) is 2,019; [variant matcher](../tools/orbea_pimbo_variant_matcher.py) is 1,243. Each combines substantial parsing, browser behavior, and recovery logic.

  **Done when:** Extract focused parsing, section, and verification helpers behind stable facades. Preserve the centralized Pimbo write boundary and verify selectors/parsers against captured representative fixtures.

- [ ] **TD-037 — P2 · Debt: error handling lacks a consistent policy.**

  **Evidence:** The reviewed Python sources contain 622 broad/bare exception handlers, including 232 whose only body is `pass`. Many cleanup fallbacks are reasonable, but required operations, credential checks, source reading, and some migrations can also lose diagnostics.

  **Done when:** Distinguish required failures, optional fallbacks, and cleanup failures. Preserve stage/context/traceback where useful; narrow exception types where possible. Audit important paths first rather than mechanically replacing every catch.

## Test failures and missing verification

- [ ] **TD-038 — P2 · Observed failure: earnings heatmap fails after a manual entry.**

  **Evidence:** [test_manual_submit_updates_live_session_batch_badge_and_heatmap](../tests/test_earnings_engagement_widgets.py#L137) consistently expected one heatmap entry but observed zero. Its isolated file produced **5 passed, 1 failed** during the review.

  **Done when:** Isolate whether the mismatch is application behavior, fixture timezone/clock setup, or another cause; repair it and make the test deterministic. Cover midnight and differing service/UI timezones.

- [ ] **TD-039 — P2 · Observed failure: unrestricted pytest discovery enters local scratch folders.**

  **Evidence:** The documented root `pytest -q` invocation failed collecting inaccessible `tmp/pytest`. Running explicitly against `tests` avoided that collection error. No project test discovery configuration was found.

  **Done when:** Configure test discovery to the intended suite and exclude scratch/build/output/virtual-environment folders. The documented root command works even when unrelated scratch folders are present.

- [ ] **TD-040 — P2 · Investigation: the broader test run did not finish.**

  **Evidence:** The `tests` run progressed through hundreds of cases, displayed two failures, then stopped producing progress and was interrupted. One failure was isolated as TD-038; the other failure and the stall were not diagnosed. Do not treat the interrupted run as an overall pass.

  **Done when:** Capture the exact stalled test and stack using bounded diagnostics, isolate its cause, identify the second failure, and complete the suite. Check widget, timer, worker, and database cleanup without assuming the cause in advance.

  **Progress / remaining work (7 October 2026):** The full suite stall is now localized to test_screen_crash_regressions.py::test_batch_resize_and_info_retheme_do_not_reenter_qt, with a timeout stack in MainWindow._on_global_theme_changed. A second run excluding that file completed. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [ ] **TD-041 — P1 · Verification gap: legacy uploader integration contracts are not protected by the suite.**

  **Evidence:** The review found 52 test files and 402 named test functions, but no tests referencing the actual TranslationManager scraper call chain or uploader factory. TD-001 through TD-005 passed through existing coverage gaps.

  **Done when:** Add fixture-based contract coverage for all offered brands through their actual uploader paths, failure propagation, options, generated-source identity, and image handoff. Each relevant defect gets a regression case as it is fixed.

  **Progress / remaining work (7 October 2026):** Added offline product-data safety regressions for every adapter signature, stale sources, concurrent same-brand data, variants, selected-stage failures, identity/version checks, truthful cancellation, images and history identity. Broader UI/package coverage remains pending. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

## Dependencies, documentation, and repository hygiene

- [ ] **TD-042 — P2 · Debt: dependency/build inputs are only partially reproducible.**

  **Evidence:** [requirements.txt](../requirements.txt) pins many packages while leaving Pillow, PySide6, its addons, and Fluent Widgets open-ended. CI installs unpinned PyInstaller; [ultrabike.spec](../ultrabike.spec) includes Qt/runtime workarounds tied to particular environments.

  **Done when:** Define reproducible supported runtime/build dependencies and an intentional upgrade process. Validate the frozen executable's smoke checks when Qt, Fluent Widgets, Python, or packaging dependencies change.

- [ ] **TD-043 — P2 · Risk: navigation relies on private Fluent Widgets behavior.**

  **Evidence:** [MainWindow's navigation click guard](../GUI_Qt/MainWindow.py#L564) rewires private `_onClicked` behavior and internal item layout state. Floating Fluent Widgets versions increase the chance that those details change.

  **Done when:** Isolate the workaround in one compatibility adapter, use public APIs where sufficient, and test required navigation behavior against the supported dependency version. Unexpected incompatibility must remain diagnosable.

- [x] **TD-044 — P2 · Debt: brand option documentation disagrees with implementation.**

  **Evidence:** [brand-options.md](brand-options.md) references removed `BatchUploadScreen.py`, advertises `append_order_note` behavior absent from BaseUploader, describes Pinarello `None` as auto-detection although the scraper raises, includes incomplete constructors/incorrect class names, and uses source links that resolve under `docs` instead of the repository root.

  **Done when:** Rewrite around the actual supported single/batch/supplier workflows and validated options. Examples execute offline where practical; links resolve; unsupported/planned options are distinguished from implemented ones.

  **Fixed (7 October 2026):** Brand options documentation now describes actual Upload/Unified Batch behavior, supported options, unavailable GUI selectors, failure rules and valid relative links. See [product safety regressions](../tests/test_product_data_safety.py) and [supplier upload regressions](../tests/test_orbea_upload.py).

- [ ] **TD-045 — P3 · Debt: local scratch/output files obscure the repository and test workflow.**

  **Evidence:** Numerous local pytest variants, `tmp`, `out`, and output artifacts appear beside source; some are untracked and some are inaccessible. [.gitignore](../.gitignore) does not consistently exclude these locations and broadly ignores image/spreadsheet extensions that can also be legitimate assets/fixtures.

  **Done when:** Establish documented scratch/output locations and targeted ignore rules. Keep intentional source assets and fixtures trackable. Clean only reviewed generated artifacts; preserve collected product data and unfinished work.

- [ ] **TD-046 — P3 · Verification gap: advertised Python support exceeds the CI matrix.**

  **Evidence:** README recommends Python 3.11–3.13; [Windows CI](../.github/workflows/windows-ci.yml) tests only 3.13. CI has tests/import/package smoke checks but no configured static contract checks to catch missing-method and call-signature drift.

  **Done when:** Validate the supported Python versions or narrow the stated support. Introduce focused static checks for critical interfaces and missing members, with an incremental baseline rather than an unrelated whole-repository cleanup.

## Additional data-safety findings

- [x] **TD-047 — P1 · Reproduced defect: conflicting supplier values silently overwrite components.**

  **Evidence:** Legacy scraper dictionaries and KROSS/Orbea specification plans accepted a last value for repeated mapped fields. This can mix configurations before file validation sees them.

  **Done when:** Reject conflicting values before writing/AI; retain size-specific TREK selection and shared specifications. Fixed with SpecificationMap and explicit TREK merge validation; covered by offline scraper and plan tests.

- [x] **TD-048 — P1 · Code-confirmed defect: old or ambiguous content becomes new bike specifications.**

  **Evidence:** Standard upload guessed wheel size from the old PIMBO title and groupset from the old PIMBO spec. Octane copied a combined DERAILLEURS value to both front/rear fields. Pinarello's special tyre/hub handling bypassed the frameset filter. KROSS dropped motor/battery/negative data and truncated multi-word colour text; Factor dropped component fields solely because translations were absent.

  **Done when:** Require supplier/selected values, avoid unsupported component guesses, filter framesets before expansion, preserve collected component data, and make unmatched fields fail clearly. These paths are fixed and covered by regression tests.

- [x] **TD-049 — P1 · Risk: product navigation or concurrent changes redirect edits/save.**

  **Evidence:** Editor writes were not bound to the product verified at begin; finish did not validate identity. Automatic Save did not check that the initial version was still current. Exact-code navigation picked the first duplicate row; duplicate batch SKUs could target the same product concurrently.

  **Done when:** Bind edits to the verified product, reject identity/version changes and ambiguous/duplicate targets, and verify discard identity before reload. Guards are implemented; offline identity/version and duplicate-input regressions cover them. KROSS local packages also verify their saved product identity.

- [x] **TD-050 — P1 · Reproduced defect: missing selected supplier data is still a successful result.**

  **Evidence:** Orbea missing specification source could still pre-fill from names and report success; KROSS missing selected assets/descriptions/specs was also successful with warnings. Failed AI return values could be marked completed without an exception.

  **Done when:** Required missing data/unmatched specs/failed AI produce FAILED and block automatic Save. First-phase saves remain visible if enrichment fails afterwards. Fixed in the shared supplier workflow and its regressions.

- [ ] **TD-051 — P2 · Observed failure: earnings deadline test depends on a past fixed date.**

  **Evidence:** test_earnings_goal_presentation.py::test_goal_dialog_deadline_toggle_preserves_enabled_state_and_value_contract expected 24 August 2026 but received the current date, 7 October 2026. This appeared in the bounded full suite; it is outside the bike-data changes.

  **Done when:** Determine the intended deadline-clamping behavior and make the regression date-independent without weakening that behavior.

- [ ] **TD-052 — P2 · Observed failure: settings-save regression sees extra writes and closed-database callbacks.**

  **Evidence:** test_settings_save.py::test_settings_save_skips_redundant_global_refreshes expected two writes and observed four, including navigation_compact updates. The failure reproduces in isolation; timer callbacks can also access a closed test database during cleanup.

  **Done when:** Isolate redundant settings writes versus intended navigation updates, repair the correct contract, and stop scheduled callbacks before closing their database.

## Remaining content-verification risk

- [ ] **TD-053 — P1 · Risk: successful MagicAI execution does not prove factual accuracy.**

  **Evidence:** The editor checks application/field changes, language and workflow completion. It does not verify every generated description claim or component against the supplier source. Fresh-source requirements and fail-safe stage results address known data-mixing defects; generated facts still require review.

  **Done when:** Show generated changes against supplier evidence, detect unsupported/contradictory specifications, and require review for facts that cannot be verified before they can be treated as accurate or automatically saved.

## Orbea refactor fixes — 8 October 2026

- [x] **TD-054 — P2 · Reproduced defect: collection service classes are returned without construction.**

  **Evidence:** OrbeaWorkflowController treated a class exposing `run` and `discover_filter_options` as a ready service instance.

  **Fixed:** Classes are instantiated with the driver; supplied instances remain intact. Photo instances exposing only `run_many` are also supported. Class/callable/instance contracts are covered in [worker regressions](../tests/test_orbea_workers.py).

- [x] **TD-055 — P1 · Code-confirmed defect: failed description URLs still produce a completion message.**

  **Evidence:** The description result handler displayed “Description extraction complete” regardless of returned failures.

  **Fixed:** Failed URLs produce a partial-completion status, failure counts and a warning while keeping saved text files available. Cancelled results retain their stopped status. English/Lithuanian messages and UI regressions are included.

- [x] **TD-056 — P1 · Reproduced defect: an Orbea browser cleanup exception can retain the collection lock.**

  **Evidence:** `website.close()` ran before the lock-release statement without a protective `finally`.

  **Fixed:** Cleanup and partial-report preservation have a focused helper; the lock is always released. The original failure is retained if cleanup also fails. [Cleanup regressions](../tests/test_orbea_run_cleanup.py) verify that another run can start.

- [x] **TD-057 — P2 · Reproduced defect: internal browser-factory TypeErrors trigger another construction call.**

  **Evidence:** `_new_image_driver` caught every TypeError from the factory and retried without the browser argument, masking internal errors and potentially constructing a browser twice.

  **Fixed:** Bind the supported call signature before invoking the factory. Both existing signatures work; internal TypeErrors propagate after one call. Covered by cleanup/factory regressions.

- [x] **TD-058 — P1 · Reproduced defect: direct-job ownership and control locking diverge during completion/stop.**

  **Evidence:** A thread could finish while its result/finished signals were still queued, allowing another job to start before the prior result reached the screen. Direct jobs did not consistently lock the upload panel, and an action refresh could enable Stop again after it had been requested.

  **Fixed:** Keep ownership until the finished callback, lock every workflow's inputs centrally, preserve the active Stop button and keep it disabled after stopping. Shared startup recovery also restores controls if worker registration fails. [UI regressions](../tests/test_orbea_upload_ui.py) cover these boundaries.

- [x] **TD-059 — P1 · Reproduced defect: final report failure can leave a completed checkpoint.**

  **Evidence:** A checkpoint could already be marked complete when final report writing failed; the returned failure then still carried `completed=True`.

  **Fixed:** Finalization marks the checkpoint incomplete, records the original error, preserves available reports and releases the run lock. The cleanup regressions verify both returned and persisted completion state.

## Suggested repair sequence

1. Repair source identity and scraper/image contracts: TD-001–007, protected by TD-041.
2. Repair batch options/progress and required preflight behavior: TD-008–013.
3. Establish file, browser, and database ownership; make stop/shutdown truthful: TD-014–023.
4. Resolve observed test failures and complete a bounded full suite: TD-038–040.
5. Refactor behind those validated boundaries: TD-024–037. Preserve Draft guards, verified target identity, save verification, checkpoint recovery, encryption, and accounting invariants.
6. Make builds, dependency upgrades, documentation, and repository housekeeping repeatable: TD-042–046.

## Review snapshot

Counts are physical Python source lines, including comments and embedded styles/scripts; size alone is not a defect. Responsibilities and coupling determine the refactoring need.

| Measure | Observed |
| --- | ---: |
| Python source files scanned | 182 |
| Python source lines scanned | 69,280 |
| Source files above 1,000 lines | 17 |
| Test files | 52 |
| Named test functions | 402 |
| Broad/bare exception handlers | 622 |
| Broad/bare handlers containing only `pass` | 232 |

Other large files to account for when splitting related features include `GUI_Qt/earnings/dialogs.py` (1,630 lines), `GUI_Qt/earnings/widgets.py` (1,164), `GUI_Qt/screens/KrossScreen.py` (1,133), `GUI_Qt/screens/DescriptionsScreen.py` (1,036), and `GUI_Qt/screens/PinarelloImageScreen.py` (1,036). Treat these as review hotspots, not independently proven bugs.

The original assessment made no application fixes. The subsequent product-data safety pass is recorded in the completion/progress notes above; general architecture work remains open. Offline reproductions used mocks and temporary files; no live product writes were performed. Runtime/browser/site behavior beyond those checks remains unverified.

## Product-data safety validation

The safety pass used offline fixtures, mocked browser writes, temporary databases and a controlled two-thread source test. No live PIMBO product was edited. The accepted targeted command includes product safety, PIMBO workflow, KROSS/Orbea upload, supplier UI, session security, description navigation and sidebar navigation tests: **183 passed, plus five passing subtests**. Compilation of all changed Python modules also passed.

The first full suite attempt stalled in the theme-change test described under TD-040 and was interrupted. A run excluding that file completed with 491 passed, four failures and 13 passing subtests. One failure was the newly added supplier AI diagnostic assertion, repaired and rechecked in the targeted run. The other failures are TD-038, TD-051 and TD-052. Live supplier DOM changes, generated AI factual accuracy, packaged installation behavior, and the remaining general transaction/lifecycle work are not certified by these offline checks.


## Orbea refactor validation — 8 October 2026

The complete Orbea regression set plus shared product safety, Pimbo workflow and
specification-AI exclusions passed: **474 tests and 11 subtests**, with 244 unrelated
tests deselected. The UI compile/import smoke check also passed, including every
new Orbea controller. New coverage exercises cancellation during service construction,
partial description results, queued Qt result ownership, startup failure recovery,
cleanup/report failure, subsequent-run lock recovery and factory call contracts.
One existing product-safety editor mock was updated to expose the current photo
metadata dictionary. No live Pimbo product writes were performed. The broader
unrelated full-suite failures listed above were not reassessed in this pass.
