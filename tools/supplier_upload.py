"""Common supplier-to-PIMBO upload sequence used by KROSS and Orbea."""
from __future__ import annotations

import re
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from Managers.PimboProductEditor import PimAiStepResult, PimAutomationError, PimPreparationResult, PimPreparationStatus, PimboProductEditor

PIMBO_PRODUCTS_URL = "https://pim.bo.ultrabike.lt/dashboard/products"
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
PRODUCT_PHOTO_UPLOAD_BATCH_SIZE = 10
PRODUCT_PHOTO_UPLOAD_BATCH_PAUSE_SECONDS = 1.0

def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def normalize_sku(value):
    return re.sub(r"[^A-Z0-9._-]", "", str(value or "").upper())

def unique_skus(values):
    return tuple(dict.fromkeys(code for value in values if (code := normalize_sku(value))))

class SupplierUploadWorkflow:
    supplier_label = "Supplier"
    geometry_name = "dimensions-table.png"
    size_table_name = "size-height-table.png"
    required_specification_fields = ("Modelis", "Spalva", "Lako užbaigimas", "Ratų dydis")
    requires_source_specifications = False
    specification_value_migrations = (('Svoris', 'Dviračio svoris (kg)'),)

    def specification_ai_exclusions(self, match, product):
        return ()

    def validate_product_sources(self, product, selected):
        pass

    def local_photo_candidates(self, folder):
        return tuple(sorted(path for path in folder.iterdir() if path.is_file()
            and path.suffix.casefold() in IMAGE_SUFFIXES
            and path.name.casefold() not in {self.geometry_name, self.size_table_name}))

    def geometry_upload_paths(self, path):
        return (path,) if path is not None else ()

    def table_upload_paths(self, geometry, size):
        return self.geometry_upload_paths(geometry) + ((size,) if size is not None else ())

    def validate_package_target(self, saved_match, resolved_match):
        saved_id = saved_match.pimbo_product_id or self._pimbo_product_id(saved_match.pimbo_product_url)
        resolved_id = resolved_match.pimbo_product_id or self._pimbo_product_id(resolved_match.pimbo_product_url)
        if saved_id and resolved_id and saved_id != resolved_id:
            raise PimAutomationError('The local package belongs to a different PIMBO product')

    @staticmethod
    def _pimbo_product_id(url: str) -> str:
        match = re.search('/dashboard/products/([^/?#]+)', str(url or ''))
        return match.group(1) if match else ''

    def prepare_upload_batch(self, matches, *, progress=None):
        """Check existing edits before any multi-product result can be overwritten."""
        if len(matches) < 2:
            return
        current_id = self._pimbo_product_id(getattr(self.pimbo_driver, 'current_url', ''))
        if not current_id:
            return
        editor = self.editor_factory(self.pimbo_driver)
        editor.wait_ready()
        if editor.is_dirty():
            name = editor.product_name() or current_id
            raise PimAutomationError(
                f'PIMBO has an open product with unsaved changes: {name}. '
                'Save or discard its changes and return to Products before retrying. '
                'No products in this batch were processed.'
            )

    def recover_after_failed_upload(self, match: Any, *, progress: Callable[[str], None] | None=None) -> bool:
        """Reset a failed batch item without discarding another product's edits.

            A failed MagicAI or upload step can leave PIMBO's Save button dirty. If
            the batch immediately searches for the next SKU, the normal navigation
            guard correctly refuses to leave that editor and every remaining item
            appears to fail. Only reload when the open product id is the id carried
            by the failed result; otherwise stop and let the operator inspect it.
            """
        current_url = str(getattr(self.pimbo_driver, 'current_url', '') or '')
        current_id = self._pimbo_product_id(current_url)
        target_id = match.pimbo_product_id or self._pimbo_product_id(match.pimbo_product_url)
        if current_id:
            if not target_id or current_id != target_id:
                if progress:
                    progress(f'Could not safely reset {match.sku}: the open PIMBO product is not the verified failed product')
                return False
            editor = self.editor_factory(self.pimbo_driver)
            if editor.is_dirty():
                if progress:
                    progress(f'Discarding unsaved automation changes for failed {match.sku}')
                self.pimbo_driver.get(current_url)
                editor = self.editor_factory(self.pimbo_driver)
                editor.wait_ready()
                if self._pimbo_product_id(getattr(self.pimbo_driver, 'current_url', '')) != target_id:
                    raise PimAutomationError(f'The open PIMBO product changed while resetting {match.sku}')
                # A hard reload already discarded this verified failed item's
                # automation edits. PIMBO can enable Save from defaults on load;
                # that button alone cannot prove edits survived the reload.
        self.pimbo_driver.get(PIMBO_PRODUCTS_URL)
        if progress:
            progress(f'Browser reset after failed {match.sku}; continuing the batch')
        return True

    def _open_editor(self, match: Any) -> PimboProductEditor:
        """Open the target without reloading an already-open partial run."""
        current_url = str(getattr(self.pimbo_driver, 'current_url', '') or '')
        current_id = self._pimbo_product_id(current_url)
        target_id = match.pimbo_product_id or self._pimbo_product_id(match.pimbo_product_url)
        if current_id and current_id == target_id:
            return self.editor_factory(self.pimbo_driver)
        if current_id:
            current_editor = self.editor_factory(self.pimbo_driver)
            if current_editor.is_dirty():
                raise PimAutomationError('A different PIMBO product has unsaved changes; switch or save it manually first')
        self.pimbo_driver.get(match.pimbo_product_url)
        return self.editor_factory(self.pimbo_driver)

    def upload_and_save(self, match: Any, output_root: Path | None, *, options: Any=None, progress: Callable[[str], None] | None=None) -> Any:
        """Run the selected supplier stages with the shared PIMBO workflow."""
        if not match.ready:
            raise ValueError(f'SKU {match.sku} is not ready for upload')
        selected = options or self.workflow_options_type()
        if not selected.any_selected:
            raise ValueError(f'Select at least one {self.supplier_label} workflow stage')
        if selected.needs_output_folder and output_root is None and (not match.local_folder):
            raise ValueError('The selected image stages require an output folder')
        completed_stages: Any = []
        warnings: Any = []

        def require_ai_success(step):
            if not isinstance(step, PimAiStepResult) or not step.success:
                raise PimAutomationError(getattr(step, 'detail', '') or 'The selected MagicAI stage did not complete')
            return step

        def fill_specifications_with_ai():
            exclusions = self.specification_ai_exclusions(resolved_match, product)
            kwargs = {'excluded_fields': exclusions} if exclusions else {}
            return require_ai_success(editor.fill_empty_specifications_with_ai(specification_source, **kwargs))

        def add_warning(stage: str, detail: Any) -> None:
            message = f'{stage}: {_clean(detail)}'
            warnings.append(message)
            if progress:
                progress(f'Warning — {message}')
        product: Any = None
        image_root = Path(match.local_folder) if match.local_folder else Path(output_root) / normalize_sku(match.sku) if output_root is not None else None
        using_local_package = bool(image_root and image_root.is_dir())
        resolved_match = match
        if using_local_package:
            if progress:
                progress(f'Finding PIMBO product by local package SKU {match.sku}')
            pimbo = self.pimbo_client_factory(self.pimbo_driver).find_by_variant_sku(match.sku)
            if pimbo.status != 'pimbo_found':
                raise PimAutomationError(pimbo.note or f'SKU {match.sku} was not found in PIMBO')
            resolved_match = replace(match, pimbo_product_id=pimbo.pimbo_product_id, pimbo_product_name=pimbo.pimbo_product_name or match.pimbo_product_name, pimbo_product_url=pimbo.pimbo_product_url)
            # Retain the verified identity if a later preparation step raises.
            self._upload_target = resolved_match
            if progress:
                progress(f'Verified PIMBO product — {resolved_match.pimbo_product_name or resolved_match.pimbo_product_id}')
            try:
                saved_match, product = self._read_package(image_root)
                if saved_match is not None:
                    self.validate_package_target(saved_match, resolved_match)
                    product_variant_skus = product.variant_skus if product else ()
                    package_skus = unique_skus((saved_match.sku, *saved_match.variant_skus, *product_variant_skus))
                    if package_skus and normalize_sku(match.sku) not in package_skus:
                        raise PimAutomationError(f'Local package belongs to {saved_match.sku}, not {match.sku}')
            except Exception as error:
                raise PimAutomationError(f'Could not read local {self.supplier_label} package: {error}') from error
        elif selected.needs_catalogue:
            if progress:
                progress(f'Reading {self.supplier_label} source data for {match.sku}')
            product = self.public_catalog.fetch_product(self.source_url(match))
        self.validate_product_sources(product, selected)
        photo_paths: Any = ()
        if selected.product_photos:
            if using_local_package:
                if progress:
                    progress(f'Loading local {self.supplier_label} product photos for {match.sku}')
                local_photo_candidates = self.local_photo_candidates(image_root)
                photo_paths = tuple((path for path in local_photo_candidates if self._local_product_photo_is_uploadable(path)))
                skipped_thumbnails = len(local_photo_candidates) - len(photo_paths)
                if skipped_thumbnails and progress:
                    progress(f'Ignored {skipped_thumbnails} thumbnail-sized local {self.supplier_label} photo(s)')
            else:
                if progress:
                    progress(f'Downloading {self.supplier_label} product photos for {match.sku}')
                photo_paths = self.public_catalog.download_images(product, image_root, log=progress)
        dimensions_image: Any = None
        size_chart_image: Any = None
        geometry_unavailable = bool(product and getattr(product, 'geometry_unavailable', False))
        size_tables_unavailable = bool(product and getattr(product, 'size_tables_unavailable', False))
        if selected.size_tables or selected.geometry:
            if using_local_package:
                if selected.geometry:
                    candidate = image_root / self.geometry_name
                    dimensions_image = candidate if candidate.is_file() and not geometry_unavailable else None
                if selected.size_tables:
                    size_candidate = image_root / self.size_table_name
                    size_chart_image = size_candidate if size_candidate.is_file() and not size_tables_unavailable else None
                if progress:
                    progress(f'Loading selected local {self.supplier_label} table images for {match.sku}')
                missing_selected_table = (selected.geometry and dimensions_image is None and not geometry_unavailable) or (selected.size_tables and size_chart_image is None and not size_tables_unavailable)
                source_url = (product.url if product else '') or self.source_url(match)
                if missing_selected_table and source_url:
                    if progress:
                        progress(f'Local {self.supplier_label} table image is missing; recapturing it for {match.sku}')
                    source_product = product or self.product_data_type(source_url, self.source_name(match), '', '', ())
                    if source_product.url != source_url:
                        source_product = replace(source_product, url=source_url)
                    try:
                        captured_dimensions = self.public_catalog.capture_dimensions(source_product, image_root / self.geometry_name, log=progress)
                        if selected.geometry:
                            dimensions_image = captured_dimensions
                        if selected.size_tables:
                            size_candidate = image_root / self.size_table_name
                            size_chart_image = size_candidate if size_candidate.is_file() else None
                    except Exception as error:
                        add_warning(f'{self.supplier_label} tables', f'Could not recapture missing table: {error}')
            else:
                if progress:
                    progress(f'Capturing the full {self.supplier_label} dimensions table for {match.sku}')
                captured_dimensions = self.public_catalog.capture_dimensions(product, image_root / self.geometry_name, log=progress)
                if selected.geometry:
                    dimensions_image = captured_dimensions
                if selected.size_tables:
                    size_candidate = image_root / self.size_table_name
                    size_chart_image = size_candidate if size_candidate.is_file() else None
            if selected.geometry and dimensions_image is None and not geometry_unavailable:
                add_warning('Geometry', f'No dimensions table was found in {image_root}')
            if selected.size_tables and size_chart_image is None and not size_tables_unavailable:
                add_warning('Size tables', f'No SIZE/HEIGHT table was found in {image_root}')
        table_paths = self.table_upload_paths(dimensions_image, size_chart_image)
        downloaded_image_paths = photo_paths + table_paths
        if using_local_package and progress:
            progress(f"Local package preflight — photos: {len(photo_paths)}; Geometry: {('yes' if dimensions_image else 'no')}; Size tables: {('yes' if size_chart_image else 'no')}; description: {(len(product.description_html) if product else 0)} chars; specifications: {(len(product.specification_text) if product else 0)} chars")
        if progress:
            progress('Preparing the verified PIMBO Draft product')
        editor = self._open_editor(resolved_match)
        base = editor.begin('')
        base = replace(base, product_code=resolved_match.sku)
        if base.status == PimPreparationStatus.BLOCKED_NON_DRAFT:
            return self.upload_result_type(match=resolved_match, preparation=base, downloaded_images=downloaded_image_paths, product=product, dimensions_image=dimensions_image, size_chart_image=size_chart_image, options=selected, completed_stages=tuple(completed_stages))
        changed_fields: Any = []
        photo_upload: dict[str, Any] = {}
        ai_steps: Any = []
        family_ready: Any = None
        description_ready: Any = None
        description_unavailable = bool(product and getattr(product, 'description_unavailable', False))
        unsafe_phase_one = False
        raw_specification_source = product.specification_text if (selected.specifications_prefill or selected.specifications_magic_ai) and product else ''
        missing_required_source = bool((selected.specifications_magic_ai or
            (self.requires_source_specifications and selected.specifications_prefill)) and not raw_specification_source.strip())
        if missing_required_source:
            add_warning('Source specifications', f'No saved {self.supplier_label} component specifications were found; collect them before running specification stages')
        specification_plan: Any = None
        specification_prefill_ready = not missing_required_source
        if selected.specifications_prefill:
            variant_sizes: Any = ()
            try:
                if progress:
                    progress(f'Reading PIMBO variant frame sizes for {self.supplier_label} pre-fill')
                variant_sizes = tuple(editor.collect_variant_sizes())
                if variant_sizes:
                    if progress:
                        progress(f"Variant frame sizes read — {', '.join(variant_sizes)}")
                else:
                    specification_prefill_ready = False
                    if selected.save:
                        unsafe_phase_one = True
                    add_warning(f'{self.supplier_label} specification pre-fill', 'No frame sizes were found in PIMBO Variants; the product was not pre-filled or saved')
            except Exception as error:
                specification_prefill_ready = False
                if selected.save:
                    unsafe_phase_one = True
                add_warning(f'{self.supplier_label} specification pre-fill', f'Variant sizes: {error}')
            source_name = resolved_match.pimbo_product_name or str((base.initial_fields or {}).get('product_name_lt') or '') or editor.product_name()
            specification_plan = self.build_specification_plan(source_name, variant_sizes, raw_specification_source, translator=self.translation_handler, product=product)
            planned_values = dict(specification_plan.values)
            required_name_fields = self.required_specification_fields
            missing_name_fields = tuple((name for name in required_name_fields if not _clean(planned_values.get(name, ''))))
            if missing_name_fields:
                specification_prefill_ready = False
                if selected.save:
                    unsafe_phase_one = True
                add_warning(f'{self.supplier_label} specification pre-fill', f"Could not extract required product-name fields: {', '.join(missing_name_fields)}; the product was not pre-filled or saved")
            elif specification_prefill_ready and progress:
                progress(f"Verified {self.supplier_label} pre-fill data — {planned_values.get('Modelis', '')}; {planned_values.get('Spalva', '')}; {planned_values.get('Lako užbaigimas', '')}; {planned_values.get('Ratų dydis', '')}; {planned_values.get('Galimi rėmo dydžiai', '')}")
        specification_source = specification_plan.magic_ai_source if specification_plan is not None else raw_specification_source
        if selected.specifications_magic_ai and (not specification_source):
            add_warning('Specifications MagicAI', f'{self.metadata_name} has no saved {self.supplier_label} specifications usable by MagicAI')

        def ordered_completed_stages() -> tuple[str, ...]:
            return tuple((stage for stage in self.workflow_options_type.STAGES if stage in completed_stages))

        def normalize_preparation(preparation: PimPreparationResult) -> PimPreparationResult:
            if warnings:
                return replace(preparation, status=PimPreparationStatus.FAILED,
                    warnings=tuple(warnings), error='Selected stages did not complete: ' + '; '.join(warnings))
            if preparation.status == PimPreparationStatus.FAILED and preparation.error == 'PIMBO form has no reviewable unsaved changes':
                return replace(preparation, status=PimPreparationStatus.NO_CHANGES, error='', warnings=tuple(warnings))
            return replace(preparation, warnings=tuple(warnings))

        def make_result(preparation: PimPreparationResult) -> Any:
            preparation = replace(preparation, photo_upload=dict(photo_upload))
            return self.upload_result_type(match=resolved_match, preparation=preparation, downloaded_images=downloaded_image_paths, product=product, dimensions_image=dimensions_image, size_chart_image=size_chart_image, options=selected, completed_stages=ordered_completed_stages())

        def apply_specification_prefill(target_changes: list[str]) -> None:
            if specification_plan is None:
                return
            available = 0
            changed = 0
            results = editor.set_specifications(specification_plan.values, overwrite=True, move_if_empty=self.specification_value_migrations)
            changed_names: Any = []
            missing_names: Any = []

            def remember_changed(name: str) -> None:
                if name not in changed_names:
                    changed_names.append(name)
            for name, _value in specification_plan.values:
                result = results.get(name)
                if result is None:
                    missing_names.append(name)
                    continue
                available += 1
                if result:
                    remember_changed(name)
            for name in ('Svoris', 'Dviračio svoris (kg)'):
                if results.get(name):
                    remember_changed(name)
            for name in changed_names:
                target_changes.append(f'specification:{name}')
            changed = len(changed_names)
            if missing_names:
                raise PimAutomationError('Required specification fields were not found: ' + ', '.join(missing_names))
            if available == 0:
                raise PimAutomationError(f'The current PIMBO family has none of the {self.supplier_label} pre-fill fields')
            if 'specifications_prefill' not in completed_stages:
                completed_stages.append('specifications_prefill')
            if progress:
                progress(f'{self.supplier_label} specification pre-fill replaced {changed} of {available} available field(s)')
        if selected.product_photos:
            uploaded_photo_count = 0
            try:
                inspect_photos = getattr(editor, 'prepare_product_photo_upload', None)
                should_upload = inspect_photos(has_replacements=bool(photo_paths)) if callable(inspect_photos) else bool(photo_paths)
                photo_upload = dict(getattr(editor, 'photo_upload', {}) or {})
                if photo_upload.get('placeholders_removed'):
                    changed_fields.append('images')
                if photo_upload.get('action') == 'skipped_existing':
                    if progress:
                        progress('Product photos skipped because PIMBO already has real photos')
                elif not photo_paths:
                    raise PimAutomationError(f'No product photos were found in {image_root}' if using_local_package else f'No {self.supplier_label} product photos could be downloaded')
                total_photos = len(photo_paths) if should_upload else 0
                batches = tuple((photo_paths[index:index + PRODUCT_PHOTO_UPLOAD_BATCH_SIZE] for index in range(0, total_photos, PRODUCT_PHOTO_UPLOAD_BATCH_SIZE)))
                for batch_index, batch in enumerate(batches):
                    first = batch_index * PRODUCT_PHOTO_UPLOAD_BATCH_SIZE + 1
                    last = first + len(batch) - 1
                    if progress:
                        progress(f'Uploading {self.supplier_label} product photos {first}–{last} of {total_photos}')
                    uploaded_photo_count += editor.upload_product_images(batch, skip_if_present=False)
                    if batch_index < len(batches) - 1:
                        if progress:
                            progress('Waiting for PIMBO to register the photo batch')
                        time.sleep(PRODUCT_PHOTO_UPLOAD_BATCH_PAUSE_SECONDS)
                if uploaded_photo_count:
                    changed_fields.append('images')
                completed_stages.append('product_photos')
            except Exception as error:
                add_warning('Product photos', error)
                photo_upload.update(action='failed', error=str(error))
            finally:
                observed = dict(getattr(editor, 'photo_upload', {}) or {})
                photo_upload = {**observed, **photo_upload} if photo_upload.get('action') == 'failed' else observed
                photo_upload.setdefault('action', 'uploaded' if uploaded_photo_count else 'missing_photos')
                photo_upload['uploaded_photos'] = uploaded_photo_count
                if (uploaded_photo_count or photo_upload.get('placeholders_removed')) and 'images' not in changed_fields:
                    changed_fields.append('images')
        if size_chart_image is not None:
            try:
                if progress:
                    progress(f'Uploading the {self.supplier_label} SIZE/HEIGHT crop to Size tables')
                if editor.upload_size_table_images((size_chart_image,), skip_if_present=False):
                    changed_fields.append('size_table_images')
                completed_stages.append('size_tables')
            except Exception as error:
                add_warning('Size tables', error)
        if dimensions_image is not None:
            try:
                if progress:
                    progress(f'Uploading the full {self.supplier_label} table to Geometry')
                if editor.upload_geometry_images(self.geometry_upload_paths(dimensions_image), skip_if_present=False):
                    changed_fields.append('geometry_images')
                completed_stages.append('geometry')
            except Exception as error:
                add_warning('Geometry', error)
        for stage, unavailable in (("geometry", geometry_unavailable), ("size_tables", size_tables_unavailable)):
            if getattr(selected, stage) and unavailable:
                completed_stages.append(stage)
                if progress:
                    progress(f'{self.supplier_label} does not publish {stage.replace("_", " ")}; skipping that upload')
        if selected.description_source:
            if description_unavailable:
                if progress:
                    progress(f'{self.supplier_label} does not publish a source description; keeping the PIMBO description')
                completed_stages.append('description_source')
            elif not product or not product.description_html:
                description_ready = False
                add_warning('Description source', f'{self.metadata_name} has no saved {self.supplier_label} description')
            else:
                try:
                    if progress:
                        progress(f'Pasting and verifying the {self.supplier_label} source description')
                    if editor.set_description_html(self._description_html(product)):
                        changed_fields.append('description_lt_source')
                    description_ready = True
                    completed_stages.append('description_source')
                except Exception as error:
                    description_ready = False
                    add_warning('Description source', error)
        if selected.description_magic_ai:
            if description_unavailable:
                if progress:
                    progress('Description MagicAI skipped because no source description is published')
                completed_stages.append('description_magic_ai')
            elif description_ready is False:
                unsafe_phase_one = True
                add_warning('Description MagicAI', f'Skipped because the {self.supplier_label} description was not pasted successfully')
            else:
                try:
                    if progress:
                        progress('Running MagicAI for the verified non-empty description')
                    description_step = require_ai_success(editor.generate_description())
                    ai_steps.append(description_step)
                    if progress and description_step.detail:
                        progress(description_step.detail)
                    completed_stages.append('description_magic_ai')
                except Exception as error:
                    unsafe_phase_one = True
                    add_warning('Description MagicAI', error)
        if selected.product_family:
            try:
                if progress:
                    progress('Setting and verifying product family Dviračiai')
                if editor.ensure_product_family('Dviračiai'):
                    changed_fields.append('product_family')
                completed_stages.append('product_family')
                family_ready = True
            except Exception as error:
                family_ready = False
                if selected.save:
                    unsafe_phase_one = True
                add_warning('Product family', error)
        if selected.brand:
            try:
                if progress:
                    progress(f'Setting brand to {self.supplier_label}')
                if editor.set_brand(f'{self.supplier_label}'):
                    changed_fields.append('brand')
                completed_stages.append('brand')
            except Exception as error:
                if selected.save:
                    unsafe_phase_one = True
                add_warning('Brand', error)
        if selected.category_magic_ai:
            try:
                if family_ready is False:
                    raise PimAutomationError('Product family Dviračiai could not be prepared')
                if not selected.product_family:
                    current_family = editor.product_family()
                    if current_family.casefold() != 'dviračiai'.casefold():
                        raise PimAutomationError(f"Product family is {current_family or 'empty'}, expected Dviračiai")
                if progress:
                    progress('Running MagicAI for the Dviračiai category')
                category_step = require_ai_success(editor.suggest_category('Dviračiai'))
                ai_steps.append(category_step)
                if progress and category_step.detail:
                    progress(f'Category selected — {category_step.detail}')
                completed_stages.append('category_magic_ai')
            except Exception as error:
                unsafe_phase_one = True
                add_warning('Category MagicAI', error)
        if selected.translations:
            try:
                if progress:
                    progress('Checking the Lithuanian product name before translation')
                if editor.ensure_lithuanian_name_from_english():
                    changed_fields.append('product_name_lt_from_en')
                    if progress:
                        progress('Lithuanian name was empty — copied the English name as the translation source')
                if progress:
                    progress('Translating product copy with overwrite existing translations enabled')
                ai_steps.append(require_ai_success(editor.translate_lt_to_all(overwrite=True)))
                completed_stages.append('translations')
            except Exception as error:
                unsafe_phase_one = True
                add_warning('Translations', error)
        specification_stage_requested = selected.specifications_prefill or bool(selected.specifications_magic_ai and specification_source)
        if specification_stage_requested and family_ready is None:
            try:
                current_family = editor.product_family()
                family_ready = current_family.casefold() == 'dviračiai'.casefold()
                if not family_ready:
                    add_warning(f'{self.supplier_label} specifications', f"Product family is {current_family or 'empty'}, expected Dviračiai")
                    if selected.save:
                        unsafe_phase_one = True
            except Exception as error:
                family_ready = False
                add_warning(f'{self.supplier_label} specifications family check', error)
                if selected.save:
                    unsafe_phase_one = True
        if specification_stage_requested and family_ready is not False and (not selected.save):
            if selected.specifications_prefill and specification_prefill_ready:
                try:
                    if progress:
                        progress(f'Replacing {self.supplier_label} name, variant, and translated specification values')
                    apply_specification_prefill(changed_fields)
                except Exception as error:
                    specification_prefill_ready = False
                    add_warning(f'{self.supplier_label} specification pre-fill', error)
            if selected.specifications_magic_ai and specification_source and specification_prefill_ready:
                try:
                    if progress:
                        progress('Running MagicAI for remaining empty Specifications')
                    specification_step = fill_specifications_with_ai()
                    ai_steps.append(specification_step)
                    if specification_step.changed:
                        changed_fields.append('specifications')
                    completed_stages.append('specifications_magic_ai')
                except Exception as error:
                    add_warning('Specifications MagicAI', error)
        if any((stage in completed_stages for stage in ('description_source', 'description_magic_ai', 'category_magic_ai', 'translations'))):
            try:
                editor.switch_locale('lt')
            except Exception as error:
                add_warning('Return to LT locale', error)
        prepared = normalize_preparation(editor.finish(base, changed_fields=changed_fields, ai_steps=ai_steps, warnings=warnings))
        if not selected.save:
            return make_result(prepared)
        if unsafe_phase_one:
            prepared = replace(prepared, status=PimPreparationStatus.FAILED, warnings=tuple(warnings), error='Automatic Save was blocked because a required stage failed; the product was left unsaved. ' + prepared.error)
            return make_result(prepared)
        if prepared.status == PimPreparationStatus.READY_FOR_REVIEW:
            if progress:
                progress(f'Saving completed first-phase {self.supplier_label} changes')
            try:
                prepared = normalize_preparation(editor.save_and_verify(prepared))
            except Exception as error:
                add_warning('First save', error)
                prepared = replace(prepared, status=PimPreparationStatus.FAILED, warnings=tuple(warnings), error=f'First save: {_clean(error)}')
            if prepared.status == PimPreparationStatus.SAVED_AUTOMATICALLY:
                completed_stages.append('save')
        if prepared.status not in {PimPreparationStatus.SAVED_AUTOMATICALLY, PimPreparationStatus.NO_CHANGES}:
            return make_result(prepared)
        if specification_stage_requested:
            if prepared.status == PimPreparationStatus.SAVED_AUTOMATICALLY:
                if progress:
                    progress('Waiting 1 second for the Dviračiai specification schema')
                time.sleep(1.0)
            if progress:
                progress('Opening Specifications after Save')
            specifications_base = replace(editor.begin(''), product_code=resolved_match.sku)
            if specifications_base.status == PimPreparationStatus.BLOCKED_NON_DRAFT:
                return make_result(specifications_base)
            specification_ai_steps: Any = []
            specification_changes: Any = []
            if selected.specifications_prefill and specification_prefill_ready:
                try:
                    if progress:
                        progress(f'Replacing {self.supplier_label} name, variant, and translated specification values')
                    apply_specification_prefill(specification_changes)
                except Exception as error:
                    specification_prefill_ready = False
                    add_warning(f'{self.supplier_label} specification pre-fill', error)
            if selected.specifications_magic_ai and specification_source and specification_prefill_ready:
                try:
                    if progress:
                        progress('Running MagicAI for remaining empty Specifications')
                    specification_step = fill_specifications_with_ai()
                    specification_ai_steps.append(specification_step)
                    if specification_step.changed:
                        specification_changes.append('specifications')
                    completed_stages.append('specifications_magic_ai')
                except Exception as error:
                    add_warning('Specifications MagicAI', error)
                    specification_prefill_ready = False
            specifications_prepared = normalize_preparation(editor.finish(specifications_base, changed_fields=specification_changes, ai_steps=specification_ai_steps, warnings=warnings))
            if not specification_prefill_ready:
                specifications_prepared = replace(specifications_prepared, status=PimPreparationStatus.FAILED, warnings=tuple(warnings), error='Specification enrichment failed; the product was left with unsaved specification changes')
            if specifications_prepared.status == PimPreparationStatus.READY_FOR_REVIEW:
                if progress:
                    progress(f'Saving {self.supplier_label} specification changes')
                try:
                    specifications_prepared = normalize_preparation(editor.save_and_verify(specifications_prepared))
                except Exception as error:
                    add_warning('Specifications save', error)
                    specifications_prepared = replace(specifications_prepared, status=PimPreparationStatus.FAILED, warnings=tuple(warnings), error=f'Specifications save: {_clean(error)}')
            combined_status = specifications_prepared.status
            if combined_status == PimPreparationStatus.NO_CHANGES and prepared.status == PimPreparationStatus.SAVED_AUTOMATICALLY:
                combined_status = prepared.status
            prepared = replace(specifications_prepared, product_code=resolved_match.sku, initial_version=base.initial_version, initial_fields=base.initial_fields, status=combined_status, changed_fields=tuple(dict.fromkeys((*prepared.changed_fields, *specifications_prepared.changed_fields))), ai_steps=tuple((*prepared.ai_steps, *specifications_prepared.ai_steps)), warnings=tuple(warnings))
            if prepared.status == PimPreparationStatus.SAVED_AUTOMATICALLY:
                completed_stages.append('save')
        if progress:
            progress(f"Completed stages — {', '.join(ordered_completed_stages()) or 'none'}; warnings: {len(warnings)}")
        return make_result(prepared)
