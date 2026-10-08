from types import SimpleNamespace
from unittest.mock import patch

from tools.orbea_automation.pimbo import PimboBrowserClient


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, duration):
        self.now += duration


class PageInput:
    def __init__(self):
        self.value = "22"
        self.keys = []

    def get_attribute(self, name):
        return self.value if name == "value" else "23"

    def send_keys(self, *values):
        self.keys.extend(values)


class DelayedTableDriver:
    current_url = "https://pim.bo/dashboard/products"

    def __init__(self, clock):
        self.clock = clock
        self.page_input = PageInput()
        self.transition_at = None
        self.number_updates = []
        self.old_rows = [SimpleNamespace(identity=f"old-{index}") for index in range(50)]
        self.new_rows = [SimpleNamespace(identity=f"new-{index}") for index in range(19)]

    def find_elements(self, by, selector):
        if "input[type='number']" in selector:
            return [self.page_input]
        if "tbody tr" in selector:
            if self.transition_at is not None and self.clock.now - self.transition_at >= 0.9:
                return self.new_rows
            return self.old_rows
        if selector == "main table":
            return [object()]
        return []

    def execute_script(self, source, *args):
        if "HTMLInputElement.prototype" in source:
            self.page_input.value = args[1]
            self.number_updates.append(args[1])
            self.transition_at = self.clock.now
        elif args:
            return [row.identity for row in args[0]]
        else:
            return False


def test_page_input_update_waits_for_new_short_table_instead_of_previous_full_page():
    clock = Clock()
    driver = DelayedTableDriver(clock)
    client = PimboBrowserClient(driver)
    with patch("tools.orbea_automation.pimbo.time.monotonic", clock.monotonic), patch("tools.orbea_automation.pimbo.time.sleep", clock.sleep), patch.object(client, "_safe_click", return_value=driver.page_input):
        client.go_to_page(23)
        rows = client._wait_for_rows(allow_empty=True)
    assert rows == driver.new_rows
    assert driver.number_updates == ["23"]  # No intermediate request for page 2.
    assert driver.page_input.keys == [client._keys().ENTER]
    assert clock.now - driver.transition_at >= 1.35


def test_table_must_settle_after_a_transient_empty_render():
    clock = Clock()
    driver = DelayedTableDriver(clock)
    driver.transition_at = 0.0
    original = driver.find_elements

    def rows_with_empty_transition(by, selector):
        if "tbody tr" in selector and 0.3 <= clock.now < 0.6:
            return []
        return original(by, selector)

    client = PimboBrowserClient(driver)
    with patch("tools.orbea_automation.pimbo.time.monotonic", clock.monotonic), patch("tools.orbea_automation.pimbo.time.sleep", clock.sleep), patch.object(driver, "find_elements", side_effect=rows_with_empty_transition):
        rows = client._wait_for_rows(allow_empty=True, previous_rows=tuple(row.identity for row in driver.old_rows))
    assert rows == driver.new_rows
    assert clock.now >= 1.35
