"""Execute the production browser script against scoped DOM fixtures."""
from __future__ import annotations

import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from Managers.PimboProductEditor import PimboProductEditor


DOM_RUNTIME = r"""
const payload = JSON.parse(require('fs').readFileSync(0, 'utf8'));
class Element {
  constructor(data) {
    this.tag = data.tag || 'div';
    this.attrs = data.attrs || {};
    this.text = data.text || '';
    this.type = this.attrs.type || '';
    this.children = (data.children || []).map(child => new Element(child));
    this.children.forEach(child => child.parentElement = this);
  }
  matches(selector) {
    const attribute = selector.match(/^\[([^=]+)="([^"]+)"\]$/);
    return attribute ? this.attrs[attribute[1]] === attribute[2] : this.tag === selector;
  }
  querySelectorAll(selector) {
    const selectors = selector.split(',').map(value => value.trim());
    const found = [];
    const visit = node => node.children.forEach(child => {
      if (selectors.some(part => child.matches(part))) found.push(child);
      visit(child);
    });
    visit(this);
    return found;
  }
  closest(selector) {
    for (let node = this; node; node = node.parentElement) {
      if (node.matches(selector)) return node;
    }
    return null;
  }
  cloneNode() {
    return new Element(this.toJSON());
  }
  toJSON() {
    return {tag: this.tag, attrs: this.attrs, text: this.text,
      children: this.children.map(child => child.toJSON())};
  }
  remove() {
    if (this.parentElement) {
      this.parentElement.children = this.parentElement.children.filter(child => child !== this);
    }
  }
  get innerText() {
    return [this.text, ...this.children.map(child => child.innerText)].filter(Boolean).join('\n');
  }
  get textContent() {
    return [this.text, ...this.children.map(child => child.textContent)].join('');
  }
}
const root = new Element(payload.tree);
const input = root.querySelectorAll('input').find(node => node.attrs.id === 'target');
process.stdout.write(JSON.stringify(new Function(payload.script)(input, 'Search families...')));
"""


def element(tag='div', text='', children=(), **attrs):
    return {'tag': tag, 'text': text, 'attrs': attrs, 'children': list(children)}


def read_family(tree):
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js is required for the browser-script regression fixture')
    class Driver:
        current_url = 'https://pim.bo.ultrabike.lt/dashboard/products/p1'
        def execute_script(self, script, *args):
            result = subprocess.run([node, '-e', DOM_RUNTIME],
                input=json.dumps({'tree': tree, 'script': script}),
                text=True, encoding='utf-8', capture_output=True, check=True)
            return json.loads(result.stdout)
    editor = PimboProductEditor(Driver())
    editor.open_section = lambda _: None
    editor._find_visible = lambda *args: SimpleNamespace(get_attribute=lambda _: '')
    return editor.product_family()


@pytest.mark.parametrize('heading_tag', ['h3', 'div'])
@pytest.mark.parametrize('selected', ['', 'Dviračiai', 'Elektriniai dviračiai'])
def test_family_reader_ignores_product_details_and_reads_the_selected_value(heading_tag, selected):
    tree = element(children=(element(heading_tag, 'Product Details'),
        element('label', 'Product Family *'),
        element(children=(element('input', id='target', role='combobox'),)),
        element('span', selected)))
    assert read_family(tree) == selected


def test_empty_family_does_not_read_another_fields_selected_brand():
    tree = element(children=(element('h3', 'Product Details'),
        element(children=(element('label', 'Product Family'),
            element('input', id='target', role='combobox'))),
        element(children=(element('label', 'Brand'), element('input'), element('span', 'Orbea')))))
    assert read_family(tree) == ''


def test_open_search_options_are_not_treated_as_the_selected_family():
    tree = element(children=(element('input', id='target', role='combobox'),
        element(role='listbox', children=(element('div', 'Dviračiai', role='option'),))))
    assert read_family(tree) == ''
