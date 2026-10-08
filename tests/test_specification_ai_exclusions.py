"""Exercise PIMBO's all-fields extraction while retaining manual specifications."""
from types import SimpleNamespace

import pytest

from Managers.PimboProductEditor import PimAutomationError, PimboProductEditor


class Field:
    def __init__(self, value):
        self.value = value

    def get_attribute(self, name):
        return self.value if name == "value" else ""


class AiEditor(PimboProductEditor):
    def __init__(self, values, *, generated=None, fail=False):
        super().__init__(SimpleNamespace())
        self.fields = {name: Field(value) for name, value in values.items()}
        self.generated = generated or {}
        self.fail = fail
        self.generations = 0
        self.extract_visible = False
        self.panel = SimpleNamespace(find_elements=self.find_elements)

    def open_section(self, section):
        assert section == "specifications"

    def _active_panel(self):
        return self.panel

    def find_elements(self, by, selector):
        return list(self.fields.values()) if selector.startswith("input") else ["magic"]

    def _displayed(self, elements):
        return elements

    def _field_after_label(self, name, **kwargs):
        return self.fields.get(name)

    def _find_visible(self, by, selector):
        if "textarea" in selector:
            return Field("")
        return "extract" if self.extract_visible else None

    def _set_input_value(self, field, value):
        field.value = value

    def _wait_for_stable_specification_value(self, name, expected, **kwargs):
        assert self.fields[name].value.strip() == expected

    def _wait_until(self, predicate, message, timeout=None):
        result = predicate()
        if not result:
            raise PimAutomationError(message)
        return result

    def _click(self, element):
        if element == "magic":
            self.extract_visible = True
            return
        self.generations += 1
        for name, value in self.generated.items():
            self.fields[name].value = value
        self.extract_visible = False
        if self.fail:
            raise PimAutomationError("Extraction failed partway")


@pytest.mark.parametrize("before", ["", "Manually entered"])
def test_ai_restores_blank_and_populated_manual_fields(before):
    editor = AiEditor({"Modelis": "Orbea RISE LT M30 420W 2027", "Šakė": "",
        "Ratų dydis": before, "Lako užbaigimas": before, "Spalva": before},
        generated={"Šakė": "Fox 36", "Ratų dydis": "29", "Lako užbaigimas": "Matt", "Spalva": "Red"})
    result = editor.fill_empty_specifications_with_ai("Fork: Fox 36",
        excluded_fields=("Ratų dydis", "Lako užbaigimas", "Spalva"))
    assert result.success and result.changed and result.attempts == 1
    assert result.detail == "filled 1 of 1 empty specifications"
    assert editor.fields["Šakė"].value == "Fox 36"
    assert all(editor.fields[name].value == before for name in ("Ratų dydis", "Lako užbaigimas", "Spalva"))


def test_only_manual_fields_empty_does_not_run_ai():
    editor = AiEditor({"Šakė": "Fox 36", "Ratų dydis": "", "Lako užbaigimas": ""})
    result = editor.fill_empty_specifications_with_ai("Fork: Fox 36",
        excluded_fields=("Ratų dydis", "Lako užbaigimas"))
    assert result.success and not result.changed and editor.generations == 0


def test_ai_filling_only_excluded_fields_does_not_count_as_success():
    editor = AiEditor({"Šakė": "", "Ratų dydis": ""}, generated={"Ratų dydis": "29"})
    with pytest.raises(PimAutomationError, match="filled 0 of 1"):
        editor.fill_empty_specifications_with_ai("Wheels: 29", excluded_fields=("Ratų dydis",))
    assert editor.generations == 2 and editor.fields["Ratų dydis"].value == ""


def test_failed_extraction_restores_manual_fields():
    editor = AiEditor({"Šakė": "", "Ratų dydis": ""}, generated={"Ratų dydis": "29"}, fail=True)
    with pytest.raises(PimAutomationError, match="Extraction failed partway"):
        editor.fill_empty_specifications_with_ai("Wheels: 29", excluded_fields=("Ratų dydis",))
    assert editor.fields["Ratų dydis"].value == ""


def test_ai_still_rejects_overwriting_populated_component_fields():
    editor = AiEditor({"Šakė": "Fox 36", "Variklis": "", "Ratų dydis": ""},
        generated={"Šakė": "Fox 38", "Variklis": "Shimano", "Ratų dydis": "29"})
    with pytest.raises(PimAutomationError, match="already-filled"):
        editor.fill_empty_specifications_with_ai("Motor: Shimano", excluded_fields=("Ratų dydis",))
    assert editor.fields["Ratų dydis"].value == ""


def test_default_ai_behavior_without_exclusions_is_unchanged():
    editor = AiEditor({"Ratų dydis": ""}, generated={"Ratų dydis": "29"})
    result = editor.fill_empty_specifications_with_ai("Wheel size: 29")
    assert result.success and editor.fields["Ratų dydis"].value == "29"
