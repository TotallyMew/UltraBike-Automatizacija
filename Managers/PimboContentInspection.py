"""Read-only checks of required attributes and the general-information group."""
from __future__ import annotations

import time
from Managers.PimboChoices import ATTRIBUTE_ROWS_JS


ALLOWED_EMPTY_ATTRIBUTES = {"ratų dydis", "spalva"}
GENERAL_SPECIFICATIONS_JS = r"""
const panel=arguments[0], wanted=arguments[1];
const clean=v=>(v||'').replace(/\s+/g,' ').trim();
const visible=n=>!!(n && n.getClientRects().length);
if ([...panel.querySelectorAll('[aria-busy="true"],[data-loading="true"],.animate-pulse')].some(visible)) return null;
const headings=[...panel.querySelectorAll('span,label,h3,h4,[data-slot="card-title"]')]
  .filter(n=>visible(n) && clean(n.textContent).toLowerCase()===wanted && !n.querySelector('input,textarea'));
if (headings.length!==1) return null;
const heading=headings[0];
let group=heading.parentElement;
for (let depth=0; group && depth<5 && !group.querySelector('input[placeholder="Enter value..."],textarea[placeholder="Enter value..."]'); depth++) group=group.parentElement;
if (!group) return null;
const inputs=[...group.querySelectorAll('input[placeholder="Enter value..."],textarea[placeholder="Enter value..."]')].filter(visible);
const count=[...heading.parentElement.querySelectorAll('span')].find(n=>n!==heading && /^\d+$/.test(clean(n.textContent)));
if (!inputs.length || (count && inputs.length!==Number(clean(count.textContent)))) return null;
return inputs.map(input=>{
  let label=input.id ? [...group.querySelectorAll('label')].find(n=>n.htmlFor===input.id) : null;
  for (let parent=input.parentElement, depth=0; !label && parent && parent!==group && depth<5; parent=parent.parentElement,depth++) {
    if ([...parent.querySelectorAll('input,textarea,select')].some(n=>n!==input && n.type!=='hidden')) break;
    const labels=[...parent.querySelectorAll('label,[data-field-label],span.font-medium,[data-slot="form-label"]')]
      .filter(n=>visible(n) && clean(n.textContent) && !n.closest('button') && !n.querySelector('input,textarea,select'));
    if (labels.length===1) label=labels[0];
  }
  return {name:clean(label?.textContent).replace(/\s*\*$/, '').trim(), value:clean(input.value)};
});
"""


class PimboContentInspectionMixin:
    def _stable_content_fields(self, read, message):
        signature, since = None, time.monotonic()

        def ready():
            nonlocal signature, since
            fields = read()
            if not fields or not all(row.get("name") for row in fields) or len({row["name"] for row in fields}) != len(fields):
                signature = None
                return False
            current = repr(fields)
            if current != signature:
                signature, since = current, time.monotonic()
            return fields if time.monotonic() - since >= 0.3 else False

        return self._wait_until(ready, message)

    def inspect_missing_content(self, *, expected_product_id):
        self.wait_ready()
        if not expected_product_id or self.product_id != expected_product_id:
            raise RuntimeError("Content scan is not on the verified Pimbo product")
        self.switch_locale("lt")
        version = self.current_version()
        self.open_section("attributes")

        def attributes():
            panel = self._active_panel()
            rows = self.driver.execute_script(ATTRIBUTE_ROWS_JS, panel, True) if panel else []
            return [{"name": row["name"], "required": row["required"],
                     "values": [value["label"] for value in self._selected_choices(row["input"])]} for row in rows]

        fields = self._stable_content_fields(attributes, "Required attribute fields did not become readable")
        required = [row for row in fields if row["required"] and row["name"].casefold() not in ALLOWED_EMPTY_ATTRIBUTES]
        self.open_section("specifications")
        specs = self._stable_content_fields(
            lambda: self.driver.execute_script(GENERAL_SPECIFICATIONS_JS, self._active_panel(), "bendra informacija") if self._active_panel() else [],
            "Bendra informacija specification group was missing, ambiguous or did not finish loading")
        if self.product_id != expected_product_id or version is None or self.current_version() != version:
            raise RuntimeError("Verified product identity or version changed during content inspection")
        return {"missing_attributes": [row["name"] for row in required if not row["values"]],
                "missing_specifications": [row["name"] for row in specs if not row["value"]],
                "attributes_checked": len(required), "specifications_checked": len(specs)}
