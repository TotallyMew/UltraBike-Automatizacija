"""Scoped Pimbo choice readers and setters; never commit an arbitrary search string."""
from __future__ import annotations

import re
import time

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys


def choice_matches(actual, expected, *, categories=False):
    if categories and actual.get("id") and expected.get("id"):
        return actual["id"] == expected["id"]
    return actual["label"] == expected["label"]


def choices_match(actual, expected, *, categories=False):
    remaining = list(actual)
    for choice in expected:
        index = next((index for index, value in enumerate(remaining)
                      if choice_matches(value, choice, categories=categories)), None)
        if index is None:
            return False
        remaining.pop(index)
    return not remaining


# Both scripts use the same bounded scope: never read a neighbouring form field.
CHOICE_SCOPE_JS = r"""
const input = arguments[0];
const visible = node => !!(node && node.getClientRects().length);
const clean = value => (value || '').replace(/\s+/g, ' ').trim();
let scope = input.parentElement;
for (let node = scope, depth = 0; node && depth < 6; node = node.parentElement, depth++) {
  const other = [...node.querySelectorAll('input,select,textarea')]
    .some(control => control !== input && control.type !== 'hidden' && control.type !== 'checkbox' &&
      !control.closest('[role="listbox"],[role="option"],[cmdk-list],[data-slot="command-list"],div.absolute'));
  const labels = [...node.querySelectorAll('label')].filter(label =>
    !label.closest('[role="listbox"],[role="option"],[cmdk-list],[data-slot="command-list"],div.absolute'));
  if (other || labels.length > 1) break;
  scope = node;
}
"""

SELECTED_CHOICES_JS = CHOICE_SCOPE_JS + r"""
const values = [];
const add = node => {
  const copy = node.cloneNode(true);
  copy.querySelectorAll('button,svg,input,[role="listbox"],[role="option"]').forEach(n => n.remove());
  const label = clean(node.getAttribute('data-label') || node.getAttribute('title') || copy.textContent);
  const id = node.getAttribute('data-id') || node.getAttribute('data-value') || '';
  if (label && !values.some(v => id && v.id ? v.id === id : v.label === label))
    values.push({id, label});
};
scope.querySelectorAll('[data-slot="badge"],[data-slot="combobox-chip"],[data-selected="true"],[data-selected-value]')
  .forEach(node => {if (!node.closest('[role="listbox"],[role="option"],[cmdk-list],[data-slot="command-list"],div.absolute')) add(node);});
if (!values.length) {
  scope.querySelectorAll('button').forEach(button => {
    const label = clean(button.getAttribute('aria-label') || button.getAttribute('title'));
    const parent = button.parentElement;
    if (parent && !parent.querySelector('input,label,[role="listbox"]') &&
        /remove|clear|šalinti/i.test(label)) add(parent);
  });
}
if (!values.length) {
  const copy = scope.cloneNode(true);
  copy.querySelectorAll('label,h1,h2,h3,h4,h5,h6,button,svg,input,select,textarea,[role="button"],[role="listbox"],[role="option"],[cmdk-list],[data-slot="command-list"],div.absolute')
    .forEach(node => node.remove());
  (copy.innerText || copy.textContent || '').split(/\n/).map(clean).filter(Boolean)
    .filter(value => !/^(product categories|categories|category|attributes|required|select.*|search.*|no .*|add new.*)$/i.test(value))
    .forEach(label => values.push({id:'',label}));
}
if (!values.length && document.activeElement !== input && input.getAttribute('aria-expanded') !== 'true' && clean(input.value))
  values.push({id:'',label:clean(input.value)});
return values;
"""

REMOVE_CHOICE_JS = CHOICE_SCOPE_JS + r"""
const popup = '[role="listbox"],[role="option"],[cmdk-list],[data-slot="command-list"],div.absolute';
const removable = button => {
  const label = clean(button.getAttribute('aria-label') || button.getAttribute('title'));
  return visible(button) && !button.disabled && !button.closest(popup) &&
    (/remove|clear|šalinti/i.test(label) || (!label && !clean(button.textContent) && button.querySelector('svg')));
};
// A generic icon button may be MagicAI. Only unlabelled icons inside an
// actual selected chip may be used as its removal control.
for (const chip of scope.querySelectorAll('[data-slot="badge"],[data-slot="combobox-chip"],[data-selected="true"],[data-selected-value]')) {
  if (chip.closest(popup)) continue;
  const button = [...chip.querySelectorAll('button')].find(removable);
  if (button) return button;
}
// Single-value Base UI attributes use a dedicated clear button beside the
// input rather than a chip. Never substitute a neighbouring icon button.
const clearButton = scope.querySelector('button[data-slot="combobox-clear"]');
if (clearButton && removable(clearButton)) return clearButton;
// Older markup used explicitly labelled removal buttons without chip slots.
return [...scope.querySelectorAll('button')].find(button => {
  const label = clean(button.getAttribute('aria-label') || button.getAttribute('title'));
  const parent = button.parentElement;
  return /remove|clear|šalinti/i.test(label) && removable(button) && parent &&
    !parent.querySelector('input,label,[role="listbox"]') && clean(parent.textContent);
}) || null;
"""

CATEGORY_OPTIONS_JS = CHOICE_SCOPE_JS + r"""
// Current Pimbo renders categories as an always-visible list of toggle rows.
// Keep this inside the category field's scope, separate from attribute menus.
const rows = [...scope.querySelectorAll('div[role="button"]')].filter(node =>
  visible(node) && node.querySelector('span') &&
  !node.closest('[role="listbox"],[role="option"],[cmdk-list],[data-slot="command-list"],div.absolute'));
const parents = [...new Set(rows.map(node => node.parentElement))];
return parents.length === 1 && visible(parents[0]) ? parents[0] : null;
"""

ATTRIBUTE_ROWS_JS = r"""
const panel = arguments[0];
const clean = value => (value || '').replace(/\s+/g,' ').replace(/\s*\*\s*$/, '').trim();
const visible = node => !!(node && node.getClientRects().length);
const popup = '[role="listbox"],[role="option"],[cmdk-list],[data-slot="command-list"],[data-slot="combobox-content"],div.absolute';
if ([...panel.querySelectorAll('[aria-busy="true"],[data-loading="true"],.animate-pulse')]
      .some(visible)) return [];
return [...panel.querySelectorAll('input[placeholder="Search or add new..."]')]
  .filter(input => visible(input) && !input.closest(popup)).map(input => {
    let label = input.id ? [...panel.querySelectorAll('label')].find(n => n.htmlFor === input.id) : null;
    for (let parent = input.parentElement, depth=0; !label && parent && depth<6; parent=parent.parentElement,depth++) {
      // Base UI renders an aria-hidden text input beside each combobox. It is
      // part of this field, not a neighbouring field or an attribute label.
      const other = [...parent.querySelectorAll('input,select,textarea')].some(control =>
        control !== input && visible(control) && control.type !== 'hidden' && control.type !== 'checkbox' &&
        control.getAttribute('aria-hidden') !== 'true' && !control.closest(popup));
      if (other) break;
      // font-medium also appears on dropdown addons and icon buttons. Count
      // only non-empty label text outside controls, selected chips and menus.
      const labels = [...parent.querySelectorAll('label,[data-slot="form-label"],[data-field-label],h4,.font-medium,.font-semibold')]
        .filter(node => visible(node) && clean(node.textContent) &&
          !node.closest('button,input,select,textarea,[data-slot="input-group-addon"],[data-slot="badge"],[data-slot="combobox-chip"],[data-selected="true"],' + popup) &&
          !node.querySelector('input,select,textarea'));
      const names = [...new Set(labels.map(node => clean(node.textContent)))];
      if (names.length === 1) label = labels[0];
      else if (names.length > 1) break;
    }
    return {name:clean(label?.textContent), input};
  });
"""

POPUP_JS = r"""
const input = arguments[0];
const visible = node => !!(node && node.getClientRects().length);
for (const id of (input.getAttribute('aria-controls') || input.getAttribute('aria-owns') || '').split(/\s+/)) {
  const node = document.getElementById(id);
  if (visible(node)) return node;
}
// Portal popups are accepted only when explicitly connected to this input.
for (let parent = input.parentElement, depth = 0; parent && depth < 4; parent = parent.parentElement,depth++) {
  if ([...parent.querySelectorAll('input')].some(node => node !== input && node.type !== 'hidden' && node.type !== 'checkbox' &&
        !node.closest('[role="listbox"],[role="option"],[cmdk-list],[data-slot="command-list"],div.absolute'))) break;
  const candidates = parent.querySelectorAll('[role="listbox"],[cmdk-list],[data-slot="command-list"],div.absolute');
  for (const node of candidates) {
    if (visible(node) && !node.contains(input) && node.querySelector('[role="option"],button,[role="checkbox"],input[type="checkbox"]')) return node;
  }
}
return null;
"""


class PimboChoiceMixin:
    @staticmethod
    def normalize_description_html(value):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(value or "", "html.parser")
        for node in soup.find_all(True):
            for key in list(node.attrs):
                if key.startswith("data-mce-"):
                    del node.attrs[key]
        return re.sub(r">\s+<", "><", soup.decode()).strip()

    def _attribute_rows(self):
        panel = self._active_panel()
        return self.driver.execute_script(ATTRIBUTE_ROWS_JS, panel) if panel else []

    def read_attribute_values(self):
        self.open_section("attributes")
        signature, stable_since = None, time.monotonic()
        label_problem = ""

        def ready():
            nonlocal signature, stable_since, label_problem
            label_problem = ""
            rows = self._attribute_rows()
            names = tuple(row["name"] for row in rows)
            if not names:
                signature = None
                return False
            if not all(names):
                label_problem = f"{len(rows)} fields are visible, but {names.count('')} field labels could not be identified"
                signature = None
                return False
            if len(set(names)) != len(names):
                duplicates = sorted({name for name in names if names.count(name) > 1})
                label_problem = f"fields are visible, but their labels are ambiguous: {', '.join(duplicates)}"
                signature = None
                return False
            if names != signature:
                signature, stable_since = names, time.monotonic()
            if time.monotonic() - stable_since < 0.3:
                return False
            return {row["name"]: [value["label"] for value in self._selected_choices(row["input"])] for row in rows}

        try:
            return self._wait_until(ready, "Pimbo attribute fields did not become readable")
        except TimeoutException as error:
            if label_problem:
                raise TimeoutException(f"Could not read Pimbo attributes: {label_problem}") from error
            raise

    def _selected_choices(self, field):
        return self.driver.execute_script(SELECTED_CHOICES_JS, field) or []

    def _choice_field(self, name, categories=False):
        if categories:
            return self._find_visible(By.CSS_SELECTOR, "main input[placeholder='Search categories...']")
        return next((row["input"] for row in self._attribute_rows() if row["name"] == name), None)

    def selected_categories(self):
        self.open_section("general")
        field = self._wait_until(lambda: self._choice_field("", True), "Pimbo category field did not load")
        return self._selected_choices(field)

    def _choice_popup(self, field):
        return self.driver.execute_script(POPUP_JS, field)

    def _choice_options(self, field, categories):
        if categories:
            inline = self.driver.execute_script(CATEGORY_OPTIONS_JS, field)
            if inline is not None:
                return inline
        return self._choice_popup(field)

    def _open_choice_popup(self, name, categories):
        last_error = None
        for _attempt in range(2):
            try:
                field = self._wait_until(lambda: self._choice_field(name, categories), f"Choice field {name!r} was not found")
                self._click(field)
                previous_id = getattr(field, "id", None)

                def opened():
                    nonlocal previous_id
                    current = self._choice_field(name, categories)
                    if current is None:
                        return False
                    current_id = getattr(current, "id", None)
                    if previous_id is not None and current_id != previous_id:
                        previous_id = current_id
                        self._click(current)
                    popup = self._choice_options(current, categories)
                    return (current, popup) if popup is not None else False

                return self._wait_until(opened, f"Dropdown for {name!r} did not open")
            except Exception as error:
                last_error = error
        raise RuntimeError(f"Dropdown for {name!r} did not load: {last_error}")

    def _exact_choice_option(self, popup, choice):
        return self.driver.execute_script(r"""
          const popup=arguments[0], choice=arguments[1];
          const clean=v=>(v||'').replace(/\s+/g,' ').trim();
          let matches=[...popup.querySelectorAll('[role="option"],[role="button"],button,[role="checkbox"],input[type="checkbox"],label')]
            .filter(node=>node.getClientRects().length && !node.disabled && node.getAttribute('aria-disabled')!=='true')
            .filter(node=>choice.id ? (node.getAttribute('data-id')===choice.id || node.getAttribute('data-value')===choice.id || node.getAttribute('value')===choice.id) :
              clean(node.getAttribute('data-label') || node.getAttribute('title') || node.textContent)===choice.label);
          if (!matches.length && choice.id) {
            matches=[...popup.querySelectorAll('[role="option"],[role="button"],button,[role="checkbox"],input[type="checkbox"],label')]
              .filter(node=>node.getClientRects().length && !node.disabled && node.getAttribute('aria-disabled')!=='true')
              .filter(node=>clean(node.getAttribute('data-label') || node.getAttribute('title') || node.textContent)===choice.label);
          }
          matches=matches.filter(node=>!matches.some(other=>other!==node && node.contains(other)));
          return matches.length===1 ? matches[0] : null;
        """, popup, choice)

    def _choose_existing(self, name, choice, categories):
        field, popup = self._open_choice_popup(name, categories)
        option = self._exact_choice_option(popup, choice)

        def option_ready():
            current = self._choice_field(name, categories)
            popup = self._choice_options(current, categories) if current is not None else None
            return self._exact_choice_option(popup, choice) if popup is not None else None

        if option is None:
            # Typing is allowed only after the dropdown has actually been observed.
            field.send_keys(Keys.CONTROL, "a")
            field.send_keys(choice["label"])
            option = self._wait_until(option_ready, f"Exact existing option {choice['label']!r} for {name!r} was not found")
        self._click(option)
        # Selecting an option replaces the entire Base UI input. Wait for the
        # new field before blurring it; a missing field during React's render
        # must not leave the search input focused and mistaken for a selection.
        def blur_selected():
            current = self._choice_field(name, categories)
            if current is None:
                return False
            current.send_keys(Keys.ESCAPE)
            current.send_keys(Keys.TAB)
            return True

        self._wait_until(blur_selected, f"Choice field {name!r} did not return after selection")

    def _remove_choice(self, name, categories):
        field = self._choice_field(name, categories)
        button = self.driver.execute_script(REMOVE_CHOICE_JS, field)
        if button is None:
            return False
        self._click(button)
        return True

    def _replace_choices(self, name, choices, categories=False):
        self._assert_bound_product()
        self.open_section("general" if categories else "attributes")
        self._wait_until(lambda: self._choice_field(name, categories), f"Choice field {name!r} was not found")

        def current_values():
            field = self._choice_field(name, categories)
            return self._selected_choices(field) if field is not None else []

        def matches(actual, expected):
            return choices_match(actual, expected, categories=categories)

        if matches(current_values(), choices):
            return False
        for _index in range(100):
            before = current_values()
            if not before or not self._remove_choice(name, categories):
                break
            self._wait_until(lambda: not matches(current_values(), before), f"Could not remove selected choice for {name!r}")
        for choice in choices:
            def selected():
                return any(choice_matches(value, choice, categories=categories) for value in current_values())

            if not selected():
                self._choose_existing(name, choice, categories)
                self._wait_until(selected, f"Choice {choice['label']!r} did not remain selected")
        # A transient input value is not sufficient: require stable read-back.
        since = None

        def retained():
            nonlocal since
            if not matches(current_values(), choices):
                since = None
                return False
            since = since or time.monotonic()
            return time.monotonic() - since >= 0.3

        self._wait_until(retained, f"Choices for {name!r} did not retain the complete requested set")
        return True

    def set_categories(self, categories):
        return self._replace_choices("Categories", categories, True)

    def set_attribute_values(self, name, values):
        if name.casefold() == "spalva":
            raise ValueError("Model copying must not change Spalva")
        return self._replace_choices(name, [{"id": "", "label": value} for value in values])
