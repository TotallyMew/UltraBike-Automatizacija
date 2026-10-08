from __future__ import annotations

import html
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tools.orbea_automation import CancellationToken, OrbeaAutomationService, OrbeaRunConfig
from tools.orbea_automation.catalogue import CatalogueEntry, MatchResult
from tools.orbea_automation.checkpoint import RunCheckpoint, create_run_directory
from tools.orbea_automation.website import (
    OrbeaAccessError, OrbeaWebsiteClient, SearchProduct, WEBSITE_LOOKUP_VERSION,
    parse_region_homes, parse_search_popup, parse_website_product, product_matches, template_code,
)

HOME = OrbeaWebsiteClient.HOME
AU = "https://www.orbea.com/en-au/"
ALMA = HOME + "alma-carbon"
OCCAM = AU + "occam-sl-h10"
REGIONS = f'<dialog id="zone-lang-show-all"><a href="{HOME}">English</a><a href="{AU}">English</a></dialog>'


def popup(rows=(), *, loading=False, empty=False):
    links = ''.join(f'<li><a href="{url}"><span x-text="result.name">{html.escape(name)}</span><span x-text="result.model">{code}</span></a></li>' for code, name, url in rows)
    return ('<form role="search"><input name="query"><div x-ref="searchScrollable">' + links
            + '</div><div x-show="waiting" style="' + ('' if loading else 'display: none;')
            + '\"></div><div x-show="!waiting &amp;&amp; total === 0" style="'
            + ('' if empty else 'display: none;') + '\">No results</div></form>')


class SearchBrowser:
    def __init__(self, results):
        self.results = results
        self.navigations = []
        self.current_url = HOME
        self.query = ''
        self.queries = []
        self.open = False

    def set_page_load_timeout(self, timeout):
        pass

    def get(self, url):
        self.navigations.append(url)
        self.current_url = url
        self.query = ''
        self.open = False

    @property
    def page_source(self):
        rows = self.results.get((self.current_url, self.query), ())
        return REGIONS + popup(rows, loading=not self.query, empty=bool(self.query and not rows))

    def find_elements(self, by, selector):
        if selector == 'form[role="search"] input[name="query"]':
            return [SimpleNamespace(is_displayed=lambda: self.open, clear=lambda: None, send_keys=self.search)]
        if 'toggle-form' in selector:
            return [SimpleNamespace(is_displayed=lambda: True, click=self.open_search)]
        return []

    def open_search(self):
        self.open = True

    def search(self, query):
        self.query = query
        self.queries.append((self.current_url, query))


@pytest.mark.parametrize('sku,expected', [('U10707SV', 'U107TTCC'), ('u107ttcc', 'U107TTCC'), ('UH4701AA', 'UH47TTCC'), ('U107', 'U107TTCC'), ('', ''), ('U10707SVEXTRA', ''), ('Orca M30i', '')])
def test_only_model_ttcc_codes_are_derived(sku, expected):
    assert template_code(sku) == expected


def test_regions_are_discovered_from_switcher_with_all_languages_and_international():
    source = REGIONS.replace('</dialog>', '<a href="/fr-be">French</a><a href="/en-int">International</a><a href="https://other.example/en-us">External</a><a href="/en-be/search">Search</a></dialog>')
    assert parse_region_homes(source, HOME) == (HOME, 'https://www.orbea.com/en-int/', AU, 'https://www.orbea.com/fr-be/')
    assert parse_region_homes('<main>No country selector</main>', HOME) == ()


def test_popup_waits_for_loading_and_reads_code_and_url_from_same_row():
    rows = [('U237TTCC', 'Wrong title', OCCAM), ('U907TTCC', 'Alma Carbon', ALMA), ('U907TTCC', 'External', 'https://other.example/product')]
    assert parse_search_popup(popup(rows, loading=True), HOME) is None
    assert parse_search_popup(popup(rows), HOME) == (SearchProduct('U237TTCC', 'Wrong title', OCCAM), SearchProduct('U907TTCC', 'Alma Carbon', ALMA))
    assert parse_search_popup(popup(empty=True), HOME) == ()
    assert parse_search_popup(popup(), HOME) is None
    assert parse_search_popup(popup(rows).replace('x-ref="searchScrollable"', 'x-ref="searchScrollable" style="display: none;"'), HOME) is None
    assert parse_search_popup(popup(empty=True).replace('x-ref="searchScrollable"', 'x-ref="searchScrollable" style="display: none;"'), HOME) is None


def test_search_uses_first_exact_ttcc_result_without_product_page_or_title_matching():
    browser = SearchBrowser({(HOME, 'U907TTCC'): [('U237TTCC', 'ALMA CARBON', OCCAM), ('U907TTCC', 'Completely different name', ALMA), ('U907TTCC', 'Duplicate', HOME + 'other')]})
    client = OrbeaWebsiteClient(lambda: browser, CancellationToken(), timeout=.1)
    with patch.object(client, 'fetch', side_effect=AssertionError('No product page during lookup')):
        match = client.lookup('U90709FJ', 'Orbea ALMA CARBON')
        assert client.lookup('U90701AA', 'Other name') is match
    assert match.status == 'code_match' and match.entry.product_link == ALMA
    assert browser.queries == [(HOME, 'U907TTCC')]
    assert browser.navigations == [HOME]


def test_unresolved_code_searches_every_discovered_site_and_is_cached_for_variants():
    browser = SearchBrowser({})
    client = OrbeaWebsiteClient(lambda: browser, CancellationToken(), timeout=.1)
    match = client.lookup('U23705PE', 'Ignored name')
    assert match.status == 'unmatched'
    assert client.lookup('U23708AA') is match
    assert browser.queries == [(HOME, 'U237TTCC'), (AU, 'U237TTCC')]
    assert browser.navigations == [HOME, AU]


def test_u338_colour_variants_share_one_94_region_search_and_log_reuse(tmp_path):
    config = OrbeaRunConfig(None, tmp_path, collect_product_data=True)
    checkpoint = RunCheckpoint.create(create_run_directory(tmp_path), config)
    for index, sku in enumerate(('U33805CM', 'U33805IQ')):
        checkpoint.upsert_result({'row_key': str(index), 'sku': sku, 'status': 'unmatched'})
    client = OrbeaWebsiteClient(lambda: pytest.fail('No browser needed for this test'), CancellationToken())
    client.regions = tuple(f'https://www.orbea.com/en-{first}{second}/'
                           for first in 'abcd' for second in 'abcdefghijklmnopqrstuvwxyz')[:94]
    logs, progress = [], []
    reporter = SimpleNamespace(emit=lambda *args: progress.append(args))
    with patch.object(client, '_search_results', return_value=()) as search, patch.object(client, 'lookup', wraps=client.lookup) as lookup:
        OrbeaAutomationService(object())._lookup_products(client, checkpoint, reporter, CancellationToken(), logs.append)

    assert lookup.call_count == 1
    assert [call.args for call in search.call_args_list] == [('U338TTCC', home) for home in client.regions]
    assert len(search.call_args_list) == 94
    assert all(row['status'] == 'unmatched' and row['website_lookup_status'] == 'done' for row in checkpoint.results)
    assert [row['website_lookup_source'] for row in checkpoint.results] == ['search', 'shared_result']
    assert all(row['website_lookup_query'] == 'U338TTCC' for row in checkpoint.results)
    assert 'No exact U338TTCC result in 94' in logs[0]
    assert 'Reused U338TTCC result' in logs[1] and 'no new region searches' in logs[1]
    assert sum('No exact U338TTCC result in 94' in message for message in logs) == 1
    assert sum('Finding Orbea URL:' in update[3] for update in progress) == 1
    assert any('Reusing Orbea result: U338TTCC for U33805IQ' in update[3] for update in progress)


@pytest.mark.parametrize('saved_version', [WEBSITE_LOOKUP_VERSION, WEBSITE_LOOKUP_VERSION - 1])
def test_resume_shares_current_saved_no_match_with_new_colour_variant(tmp_path, saved_version):
    config = OrbeaRunConfig(None, tmp_path, collect_product_data=True)
    checkpoint = RunCheckpoint.create(create_run_directory(tmp_path), config)
    note = 'No exact U338TTCC result in 94 Orbea country/language sites'
    checkpoint.upsert_result({'row_key': 'first', 'sku': 'U33805CM', 'status': 'unmatched', 'note': note,
                              'website_lookup_status': 'done', 'website_lookup_version': saved_version})
    checkpoint.upsert_result({'row_key': 'second', 'sku': 'U33805IQ', 'status': 'unmatched'})
    # Reload from disk so this also covers restarting the application.
    checkpoint = RunCheckpoint.load(checkpoint.run_dir, config)
    logs = []
    match = MatchResult('unmatched', 'Orbea TTCC search', None, note)
    website = SimpleNamespace(lookup=lambda *_: match)
    with patch.object(website, 'lookup', wraps=website.lookup) as lookup:
        OrbeaAutomationService(object())._lookup_products(
            website, checkpoint, SimpleNamespace(emit=lambda *_: None), CancellationToken(), logs.append)

    assert lookup.call_count == (0 if saved_version == WEBSITE_LOOKUP_VERSION else 1)
    assert all(row['status'] == 'unmatched' and row['website_lookup_version'] == WEBSITE_LOOKUP_VERSION for row in checkpoint.results)
    assert checkpoint.results[1]['website_lookup_source'] == ('saved_result' if saved_version == WEBSITE_LOOKUP_VERSION else 'shared_result')
    assert 'Reused U338TTCC result' in logs[-1] and 'no new region searches' in logs[-1]
    assert checkpoint.data['website_lookup_completed']


def test_match_in_later_region_stops_searching_and_only_uses_ttcc():
    browser = SearchBrowser({(AU, 'U237TTCC'): [('U237TTCC', 'Regional name', OCCAM)]})
    client = OrbeaWebsiteClient(lambda: browser, CancellationToken(), timeout=.1)
    assert client.lookup('U23705PE', 'Ignored name').entry.product_link == OCCAM
    assert browser.queries == [(HOME, 'U237TTCC'), (AU, 'U237TTCC')]


@pytest.mark.parametrize('matched_region_index', [0, 1, 47])
def test_94_region_scan_stops_at_exact_match_and_reuses_url_for_variants(tmp_path, matched_region_index):
    regions = [HOME]
    for first in 'abcd':
        for second in 'abcdefghijklmnopqrstuvwxyz':
            home = f'https://www.orbea.com/en-{first}{second}/'
            if home not in regions:
                regions.append(home)
    regions = tuple(regions[:94])
    matched_home = regions[matched_region_index]
    matched_url = matched_home + 'alma-carbon'
    browser = SearchBrowser({(matched_home, 'U907TTCC'): [('U907TTCC', 'Alma Carbon', matched_url)]})
    client = OrbeaWebsiteClient(lambda: browser, CancellationToken(), timeout=.1)
    client.regions = regions
    config = OrbeaRunConfig(None, tmp_path, collect_product_data=True)
    checkpoint = RunCheckpoint.create(create_run_directory(tmp_path), config)
    for index, sku in enumerate(('U90709FJ', 'U90701AA', 'U90707IR')):
        checkpoint.upsert_result({'row_key': str(index), 'sku': sku, 'status': 'unmatched'})

    with patch.object(client, 'fetch', side_effect=AssertionError('No product page during lookup')):
        OrbeaAutomationService(object())._lookup_products(
            client, checkpoint, SimpleNamespace(emit=lambda *_: None), CancellationToken(), None)
        client.lookup('U90708AA')

    assert len(regions) == 94
    assert browser.queries == [(home, 'U907TTCC') for home in regions[:matched_region_index + 1]]
    assert browser.navigations == list(regions[1:matched_region_index + 1])
    assert checkpoint.data['website_lookup_completed']
    assert all(row['catalogue_url'] == matched_url and row['status'] == 'code_match' for row in checkpoint.results)


def test_regional_failure_is_retryable_and_never_reported_as_no_match():
    client = OrbeaWebsiteClient(lambda: None, CancellationToken())
    client.regions = (HOME, AU)
    with patch.object(client, '_search_results', side_effect=[RuntimeError('load failed'), ()]):
        with pytest.raises(RuntimeError, match='incomplete'):
            client.lookup('U90709FJ')
    assert not client._matches


def test_access_check_stops_without_trying_other_regions():
    client = OrbeaWebsiteClient(lambda: None, CancellationToken())
    client.regions = (HOME, AU)
    with patch.object(client, '_search_results', side_effect=OrbeaAccessError('access check')) as search:
        with pytest.raises(OrbeaAccessError):
            client.lookup('U90709FJ')
    assert search.call_count == 1


def test_collection_lookup_ignores_catalogue_candidate_and_does_not_fetch(tmp_path):
    config = OrbeaRunConfig(None, tmp_path, collect_product_data=True)
    checkpoint = RunCheckpoint.create(create_run_directory(tmp_path), config)
    for index, sku in enumerate(('U23705PE', 'U23708AA')):
        checkpoint.upsert_result({'row_key': str(index), 'sku': sku, 'title': 'Wrong name', 'status': 'title_only', 'catalogue_url': ALMA})
    match = MatchResult('code_match', 'Orbea TTCC search', CatalogueEntry('U237', 'U237TTCC', 'Occam SL H10', product_link=OCCAM))
    website = SimpleNamespace(fetch=lambda *_: pytest.fail('No product pages during URL lookup'), lookup=lambda *_: match, regions=(HOME, AU))
    service = OrbeaAutomationService(object())
    with patch.object(website, 'lookup', wraps=website.lookup) as lookup:
        service._lookup_products(website, checkpoint, SimpleNamespace(emit=lambda *_: None), CancellationToken(), None)
    assert lookup.call_count == 1
    assert checkpoint.data['orbea_regions'] == [HOME, AU]
    assert all(row['catalogue_url'] == OCCAM and row['website_lookup_version'] == WEBSITE_LOOKUP_VERSION for row in checkpoint.results)


@pytest.mark.parametrize('code,name,sku', [('U907TTCC', 'Alma Carbon', 'U90709FJ'), ('U237TTCC', 'Occam SL H10', 'U23705PE')])
def test_current_product_code_assignment_matches_without_using_title(code, name, sku):
    initializer = html.escape(f"lang = 'en'; code = '{code}';", quote=True)
    source = (f'<nav id="product-bike-detail">Other code U999TTCC</nav><main><h1>{name}</h1>'
              f'<div id="product-bike-detail" x-init="{initializer}"><p>Fork</p><p>RockShox SID</p></div></main>')
    product = parse_website_product(source, ALMA)
    assert product.codes == (code,)
    assert product.specifications_text == 'Fork: RockShox SID'
    assert product_matches(product, sku, 'Any product title')
    assert not product_matches(product, 'U99909FJ', name)


def test_failed_model_lookup_is_not_repeated_for_every_variant_in_same_scan(tmp_path):
    config = OrbeaRunConfig(None, tmp_path, collect_product_data=True)
    checkpoint = RunCheckpoint.create(create_run_directory(tmp_path), config)
    for index, sku in enumerate(('U23705PE', 'U23708AA')):
        checkpoint.upsert_result({'row_key': str(index), 'sku': sku, 'status': 'unmatched'})
    website = SimpleNamespace(lookup=lambda *_: None)
    with patch.object(website, 'lookup', side_effect=RuntimeError('Regional lookup is incomplete')) as lookup:
        OrbeaAutomationService(object())._lookup_products(website, checkpoint, SimpleNamespace(emit=lambda *_: None), CancellationToken(), None)
    assert lookup.call_count == 1
    assert not checkpoint.data['website_lookup_completed']
    assert all(row['website_lookup_status'] == 'error' for row in checkpoint.results)
