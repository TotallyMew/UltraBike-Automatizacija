from copy import deepcopy
from pathlib import Path

from bs4 import BeautifulSoup
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tools.orbea_automation.catalogue import CatalogueEntry, CatalogueIndex, MatchResult
from tools.orbea_automation.checkpoint import RunCheckpoint, create_run_directory
from tools.orbea_automation.models import CancellationToken, OrbeaRunConfig, PimboFilterSpec, RunCancelled
from tools.orbea_automation.pimbo import PIMBO_PRODUCTS_URL, PimboBrowserClient, list_variant_code
from tools.orbea_automation.service import OrbeaAutomationService
from tools.orbea_automation.upload import OrbeaUploadService
from tools.orbea_automation.website import template_code


TITLE = 'Orbea RISE SL M20 630W 2027 Fantasy Purple C. View - Royal Plum (Gloss)'
URL = 'https://www.orbea.com/en-be/rise-sl-m20-630w'


def row(code='U34007IR +3', **fields):
    return dict(title=TITLE, visible_code=code, row_href='', brand='Orbea',
                variant_count='4', list_stock='0', list_status='Draft', **fields)


class ListBrowser:
    current_url = PIMBO_PRODUCTS_URL

    def __init__(self, pages):
        self.pages = pages
        self.page = 1
        self.reads = []

    def execute_script(self, source, *args):
        assert "document.querySelectorAll" in source and "main table tbody tr" in source
        assert 'click(' not in source and not args
        self.reads.append(self.page)
        return deepcopy(self.pages[self.page - 1])

    def get(self, *_):
        pytest.fail('List scan must not navigate to a product')

    def back(self):
        pytest.fail('List scan must not return from a product')


class ListClient(PimboBrowserClient):
    def apply_filters(self, spec):
        self.driver.page = 1

    def _totals(self):
        return sum(map(len, self.driver.pages)), len(self.driver.pages)

    def go_to_page(self, page):
        self.driver.page = page

    def _wait_for_rows(self, **kwargs):
        return self.driver.pages[self.driver.page - 1]

    def _row_snapshot(self, *_):
        pytest.fail('Scan must read the whole page together')

    def _restore_list(self, *_):
        pytest.fail('Scan must stay on the list')


def setup_scan(tmp_path, pages, **options):
    options.setdefault('filters', PimboFilterSpec(stock='Any'))
    config = OrbeaRunConfig(None, tmp_path, **options)
    checkpoint = RunCheckpoint.create(create_run_directory(tmp_path), config)
    browser = ListBrowser(pages)
    return ListClient(browser), checkpoint, config


@pytest.mark.parametrize('value,expected', [
    ('U34007IR +3', 'U34007IR'), ('u34007ir +30', 'U34007IR'),
    ('U340TTCC +3', 'U340TTCC'), ('U340 +3', 'U340'),
    ('UH4701AA +1', 'UH4701AA'), ('U34007IR / U34008IR', 'U34007IR'),
    ('', ''), ('ORCA M30i', ''), ('U34007IR3 +3', ''), ('+3', ''),
])
def test_list_code_ignores_variant_count_and_never_uses_name(value, expected):
    assert list_variant_code(value) == expected


def test_scan_reads_code_and_full_title_without_opening_product_or_variant_pages(tmp_path):
    client, checkpoint, config = setup_scan(tmp_path, [[row()]])
    client.collect(CatalogueIndex((), allow_empty=True), checkpoint, config)
    saved, = checkpoint.results
    assert saved['sku'] == 'U34007IR' and template_code(saved['sku']) == 'U340TTCC'
    assert saved['title'] == TITLE and saved['visible_code'] == 'U34007IR +3'
    assert saved['variant_count'] == 4 and saved['list_stock'] == 0
    assert saved['variant_stock'] is None
    assert saved['product_id'] == saved['product_url'] == ''
    assert saved['sku_source'] == checkpoint.data['scan_source'] == 'Pimbo product list'
    assert checkpoint.data['scan_completed'] and client.driver.reads == [1]


def test_duplicate_list_code_is_skipped_across_pages_without_merging_other_variants(tmp_path):
    first = row()
    repeated = row('u34007ir +8')
    repeated['title'] = 'Updated title'
    client, checkpoint, config = setup_scan(tmp_path, [[first], [repeated, row('U34008AA +1')]])
    client.collect(CatalogueIndex((), allow_empty=True), checkpoint, config)
    assert [item['sku'] for item in checkpoint.results] == ['U34007IR', 'U34008AA']
    assert client.driver.reads == [1, 2]


def test_actual_product_links_preserve_distinct_ids_without_opening_them(tmp_path):
    first, second = row(), row()
    first['row_href'] = '/dashboard/products/first'
    second['row_href'] = '/dashboard/products/second'
    client, checkpoint, config = setup_scan(tmp_path, [[first, second]])
    client.collect(CatalogueIndex((), allow_empty=True), checkpoint, config)
    assert [item['product_id'] for item in checkpoint.results] == ['first', 'second']
    assert checkpoint.results[0]['product_url'] == PIMBO_PRODUCTS_URL + '/first'


def test_missing_list_code_is_recorded_for_review_without_opening_product(tmp_path):
    client, checkpoint, config = setup_scan(tmp_path, [[row('')]])
    client.collect(CatalogueIndex((), allow_empty=True), checkpoint, config)
    assert checkpoint.results[0]['status'] == 'no_variant'
    assert checkpoint.results[0]['sku'] == '' and checkpoint.data['scan_completed']


def test_partial_legacy_scan_resumes_from_list_codes_even_after_title_and_count_changes(tmp_path):
    client, checkpoint, config = setup_scan(tmp_path, [[row('U34007IR +5'), row('U34008AA')]])
    saved = row()
    saved.update(row_key=PimboBrowserClient._row_key(saved, 3, 4), sku='U34009IR',
                 status='unmatched', page=3, row=4)
    checkpoint.upsert_result(saved)
    client.collect(CatalogueIndex((), allow_empty=True), checkpoint, config)
    assert [item['sku'] for item in checkpoint.results] == ['U34009IR', 'U34008AA']


def test_cancellation_preserves_read_rows_and_resume_does_not_duplicate_them(tmp_path):
    client, checkpoint, config = setup_scan(tmp_path, [[row(), row('U34008AA')]])
    token = CancellationToken()
    client.cancellation = token
    with pytest.raises(RunCancelled):
        client.collect(CatalogueIndex((), allow_empty=True), checkpoint, config,
                       row_progress=lambda *_: token.cancel())
    assert len(checkpoint.results) == 1 and not checkpoint.data['scan_completed']
    client.cancellation = CancellationToken()
    client.collect(CatalogueIndex((), allow_empty=True), checkpoint, config)
    assert len(checkpoint.results) == 2 and checkpoint.data['scan_completed']


def test_list_scan_to_packages_preserves_upload_skus_and_reuses_ttcc_lookup(tmp_path):
    browser = ListBrowser([[row(), row('U34008AA +1')]])
    lookups = []

    def lookup(sku, title):
        lookups.append(sku)
        assert template_code(sku) == 'U340TTCC' and title == TITLE
        return MatchResult('code_match', 'Orbea TTCC search',
                           CatalogueEntry('U340', 'U340TTCC', 'Rise SL M20 630W', product_link=URL))

    website = SimpleNamespace(lookup=lookup, close=lambda: None,
                              fetch=lambda *_: pytest.fail('All downloads are disabled'))
    config = OrbeaRunConfig(None, tmp_path, filters=PimboFilterSpec(stock='Any'), collect_product_data=True, download_images=False)
    # Run the real scanner and package flow against an inert list browser.
    with patch.object(PimboBrowserClient, 'apply_filters', ListClient.apply_filters), \
         patch.object(PimboBrowserClient, '_totals', ListClient._totals), \
         patch.object(PimboBrowserClient, 'go_to_page', ListClient.go_to_page), \
         patch.object(PimboBrowserClient, '_wait_for_rows', ListClient._wait_for_rows):
        result = OrbeaAutomationService(browser, website_client_factory=lambda *_: website).run(config, resume=False)
    assert result.completed and result.counts['scanned'] == result.counts['collected'] == 2
    assert lookups == ['U34007IR'] and browser.reads == [1]
    packages = OrbeaUploadService.load_local_packages(result.run_dir)
    assert {item.sku for item in packages} == {'U34007IR', 'U34008AA'}
    assert all(item.ready and item.pimbo_product_name == TITLE for item in packages)
    assert all(item.pimbo_product_id == item.pimbo_product_url == '' for item in packages)


def test_supplied_html_exposes_full_title_and_code_independently_of_completeness_labels():
    source = (Path(__file__).parent / 'fixtures' / 'orbea_pimbo_list.html').read_text(encoding='utf-8')
    soup = BeautifulSoup(source, 'html.parser')
    product, = soup.select("main table tbody tr[data-slot='table-row']")
    title = product.select_one('span.font-medium[title]')
    cells = product.find_all('td', recursive=False)
    assert title['title'] == TITLE and title.get_text(strip=True) != TITLE
    assert list_variant_code(cells[1].select_one('span.font-mono').get_text()) == 'U34007IR'
    assert [value.get_text() for value in product.select('span.font-mono')] == ['U34007IR +3', '100', 'LT', '70']
