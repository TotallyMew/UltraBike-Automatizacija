"""
Managers/DescriptionManager.py
Handles description CRUD operations and PrestaShop upload
"""

import time
from datetime import datetime
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select


class DescriptionManager:
    # Disclaimer HTML constants
    DISCLAIMER_LT = (
        '<p><em><u>Dėl skirtingų kompiuterių monitorių, telefonų ir planšetinių '
        'kompiuterių ekranų raiškos nustatymų gaminio spalva ar atspalvis '
        'skirtinguose įrenginiuose gali skirtis nuo nuotraukoje matomos gaminio '
        'spalvos ar atspalvio, t. y. gaminio spalva ar atspalvis gali nesutapti '
        'su tikrovėje matoma gaminio spalva ar atspalviu.</u></em></p>'
    )

    DISCLAIMER_EN = (
        '<p><em><u>Due to the different resolution settings of computer monitors '
        'and phone and tablet screens, the colour or shade of the product on '
        'different devices may be different from the colour or shade of the '
        'product as seen in the photo, i.e. the colour or shade of the product '
        'may not be the same as the colour or shade of the product as it '
        'appears in reality.</u></em></p>'
    )

    DISCLAIMER_LV = (
        '<p><em><u>Datoru monitoru, tālruņu un planšetdatoru ekrānu atšķirīgo '
        'izšķirtspējas iestatījumu dēļ izstrādājuma krāsa vai tonis dažādās '
        'ierīcēs var atšķirties no attēlā redzamās izstrādājuma krāsas vai toņa, '
        't. i., izstrādājuma krāsa vai tonis var atšķirties no tā krāsas vai '
        'toņa, kāds tas ir patiesībā.</u></em></p>'
    )

    # Detection substring
    DISCLAIMER_SIGNATURE = "Due to the different resolution"

    # Short description "order note" HTML constants
    ORDER_NOTE_LT = (
        '<p><b style="color:#d0121a;">Prekę galime užsakyti, dėl jos pasiekiamumo prašome teirautis!</b></p>'
    )
    ORDER_NOTE_LV = (
        '<p><b style="color:#d0121a;">Mēs varam pasūtīt produktu jums, lūdzu, noskaidrojiet tā pieejamību!</b></p>'
    )
    ORDER_NOTE_EN = (
        '<p><b style="color:#d0121a;">We can order the product for you, please inquire about its availability!</b></p>'
    )

    ORDER_NOTE_SIGNATURE_EN = "We can order the product for you"
    ORDER_NOTE_SIGNATURE_LT = "Prekę galime užsakyti"
    ORDER_NOTE_SIGNATURE_LV = "Mēs varam pasūtīt produktu"

    def __init__(self, db_manager, logger=None):
        self.db = db_manager
        self.logger = logger

    def _log(self, message, **context):
        if self.logger:
            self.logger.log("DescriptionManager", message, **context)

    def _log_error(self, message, exception=None, **context):
        from Utilities.ErrorManager import ErrorManager
        if self.logger:
            self.logger.error(
                "DescriptionManager", message, exception=exception, **context
            )
        # Show error in GUI
        if exception:
            ErrorManager.show_error("UNEXPECTED_ERROR", error=str(exception))
        else:
            ErrorManager.show_error("UNEXPECTED_ERROR", error=message)

    def append_disclaimer_if_missing(
        self, lt_html: str, en_html: str, lv_html: str
    ) -> tuple:
        """
        Append disclaimer to each language if not already present.
        Returns: (lt_html, en_html, lv_html)
        """

        if lt_html is not None and self.DISCLAIMER_SIGNATURE not in lt_html and "Dėl skirtingų kompiuterių" not in lt_html:
            lt_html += self.DISCLAIMER_LT

        if en_html is not None and self.DISCLAIMER_SIGNATURE not in en_html:
            en_html += self.DISCLAIMER_EN

        if lv_html is not None and self.DISCLAIMER_SIGNATURE not in lv_html and "Datoru monitoru" not in lv_html:
            lv_html += self.DISCLAIMER_LV

        return lt_html, en_html, lv_html

    def _order_note_present(self, html: str | None, lang_code: str) -> bool:
        if not html:
            return False
        if self.ORDER_NOTE_SIGNATURE_EN in html:
            return True
        if lang_code == "lt" and self.ORDER_NOTE_SIGNATURE_LT in html:
            return True
        if lang_code == "lv" and self.ORDER_NOTE_SIGNATURE_LV in html:
            return True
        return False

    def append_order_note_if_missing(self, lt_html: str, en_html: str, lv_html: str) -> tuple:
        """Append the short-description order note to each language if not already present."""

        if lt_html is not None and not self._order_note_present(lt_html, "lt"):
            lt_html += self.ORDER_NOTE_LT

        if en_html is not None and not self._order_note_present(en_html, "en"):
            en_html += self.ORDER_NOTE_EN

        if lv_html is not None and not self._order_note_present(lv_html, "lv"):
            lv_html += self.ORDER_NOTE_LV

        return lt_html, en_html, lv_html

    def append_order_note_to_short_description(self, driver, product_code: str) -> bool:
        """Append the order note to the PrestaShop *short description* field (per language).

        This is designed to be safe to run multiple times: it appends only if missing.
        Requirement: click the short-description wrapper before injecting HTML.
        """
        self._log("Appending order note to short description", product_code=product_code)

        def _strip_leading_empty_paragraphs(html: str | None) -> str:
            """Remove leading empty <p>...</p> blocks that TinyMCE often inserts."""
            if not html:
                return ""
            cleaned = html.strip()
            # Remove repeated leading empty paragraphs like:
            # <p></p>, <p> </p>, <p>&nbsp;</p>, <p><br></p>, <p><br data-mce-bogus="1"></p>
            empty_p = re.compile(
                r"^\s*<p>(?:\s|&nbsp;|<br\b[^>]*\/?\s*>)*<\/p>",
                re.IGNORECASE,
            )
            while True:
                new = empty_p.sub("", cleaned)
                if new == cleaned:
                    break
                cleaned = new.lstrip()
            return cleaned

        try:
            wait = WebDriverWait(driver, 10)

            try:
                current_url = driver.current_url
                if "#tab-step1" not in current_url:
                    driver.get(current_url.split("#")[0] + "#tab-step1")
                    time.sleep(1)
            except Exception:
                pass

            languages = [
                ("lt", self.ORDER_NOTE_LT, "2"),
                ("en", self.ORDER_NOTE_EN, "1"),
                ("lv", self.ORDER_NOTE_LV, "3"),
            ]

            any_updated = False

            for lang_code, note_html, lang_id in languages:
                # Switch language so we're editing the visible locale.
                try:
                    language_dropdown = wait.until(
                        EC.element_to_be_clickable((By.ID, "form_switch_language"))
                    )
                    Select(language_dropdown).select_by_value(lang_code)
                    time.sleep(0.8)
                except Exception:
                    # Best effort; continue.
                    pass

                # Click the wrapper (per user requirement).
                try:
                    wrapper = wait.until(
                        EC.presence_of_element_located((By.ID, "form_step1_description_short"))
                    )
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});", wrapper
                    )
                    try:
                        wrapper.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", wrapper)
                    time.sleep(0.1)
                except Exception:
                    # If wrapper isn't found, we still try to locate the editor.
                    pass

                # Preferred: TinyMCE iframe like the full description field.
                iframe_id = f"form_step1_description_short_{lang_id}_ifr"
                try:
                    wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, iframe_id)))
                    editor_body = wait.until(EC.presence_of_element_located((By.ID, "tinymce")))

                    current_html = ""
                    try:
                        current_html = editor_body.get_attribute("innerHTML") or ""
                    except Exception:
                        current_html = ""

                    current_html = _strip_leading_empty_paragraphs(current_html)

                    if not self._order_note_present(current_html, lang_code):
                        new_html = (current_html or "") + note_html
                        driver.execute_script(
                            "arguments[0].innerHTML = arguments[1];",
                            editor_body,
                            new_html,
                        )
                        any_updated = True

                    driver.switch_to.default_content()
                    time.sleep(0.2)
                    continue

                except Exception:
                    try:
                        driver.switch_to.default_content()
                    except Exception:
                        pass

                # Fallback: plain textarea field.
                try:
                    textarea_id = f"form_step1_description_short_{lang_id}"
                    textarea = wait.until(EC.presence_of_element_located((By.ID, textarea_id)))
                    current_value = textarea.get_attribute("value") or ""

                    current_value = _strip_leading_empty_paragraphs(current_value)

                    if not self._order_note_present(current_value, lang_code):
                        new_value = (current_value or "") + note_html
                        driver.execute_script(
                            """
                            const el = arguments[0];
                            const value = arguments[1];
                            el.focus();
                            el.value = value;
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            """,
                            textarea,
                            new_value,
                        )
                        any_updated = True
                    time.sleep(0.2)
                except Exception:
                    # If this language field isn't available, skip.
                    continue

            self._log(
                "Short description order note processed",
                product_code=product_code,
                updated=any_updated,
            )
            return True

        except Exception as e:
            self._log_error(
                "Failed to append order note to short description",
                exception=e,
                product_code=product_code,
            )
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
            return False

    def save_description(
        self, name: str, description_lt: str, description_en: str, description_lv: str
    ) -> bool:
        """Save or update description in database"""
        self._log("Saving description", name=name)

        try:
            cursor = self.db.conn.cursor()

            existing = cursor.execute(
                "SELECT id FROM descriptions WHERE name = ?", (name,)
            ).fetchone()

            if existing:
                cursor.execute(
                    """
                    UPDATE descriptions
                    SET description_lt = ?, description_en = ?, description_lv = ?,
                        updated_at = ?
                    WHERE name = ?
                    """,
                    (
                        description_lt,
                        description_en,
                        description_lv,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        name,
                    ),
                )
                self._log("Description updated", name=name)
            else:
                cursor.execute(
                    """
                    INSERT INTO descriptions
                    (name, description_lt, description_en, description_lv)
                    VALUES (?, ?, ?, ?)
                    """,
                    (name, description_lt, description_en, description_lv),
                )
                self._log("Description created", name=name)

            self.db.conn.commit()
            return True

        except Exception as e:
            self._log_error("Failed to save description", exception=e, name=name)
            return False

    def load_description(self, name: str) -> dict | None:
        """Load description from database"""
        self._log("Loading description", name=name)

        try:
            cursor = self.db.conn.cursor()
            result = cursor.execute(
                """
                SELECT name, description_lt, description_en, description_lv,
                       created_at, updated_at
                FROM descriptions
                WHERE name = ?
                """,
                (name,),
            ).fetchone()

            if not result:
                return None

            return {
                "name": result["name"],
                "description_lt": result["description_lt"] or "",
                "description_en": result["description_en"] or "",
                "description_lv": result["description_lv"] or "",
                "created_at": result["created_at"],
                "updated_at": result["updated_at"],
            }

        except Exception as e:
            self._log_error("Failed to load description", exception=e, name=name)
            return None

    def list_descriptions(self) -> list:
        """Get list of all description names"""
        try:
            cursor = self.db.conn.cursor()
            results = cursor.execute(
                """
                SELECT name, updated_at
                FROM descriptions
                ORDER BY updated_at DESC
                """
            ).fetchall()

            return [{"name": r["name"], "updated_at": r["updated_at"]} for r in results]

        except Exception as e:
            self._log_error("Failed to list descriptions", exception=e)
            return []

    def delete_description(self, name: str) -> bool:
        """Delete description from database"""
        self._log("Deleting description", name=name)

        try:
            cursor = self.db.conn.cursor()
            cursor.execute("DELETE FROM descriptions WHERE name = ?", (name,))
            self.db.conn.commit()
            self._log("Description deleted", name=name)
            return True

        except Exception as e:
            self._log_error("Failed to delete description", exception=e, name=name)
            return False

    def upload_to_prestashop(
        self, driver, product_code: str, name: str, append_disclaimer: bool = False
    ) -> bool:
        """Upload description to PrestaShop product from database"""

        self._log(
            "Uploading description to PrestaShop",
            product_code=product_code,
            name=name,
            append_disclaimer=append_disclaimer,
        )

        desc = self.load_description(name)
        if not desc:
            self._log_error("Description not found", name=name)
            return False

        lt_html = desc["description_lt"]
        en_html = desc["description_en"]
        lv_html = desc["description_lv"]

        if append_disclaimer:
            lt_html, en_html, lv_html = self.append_disclaimer_if_missing(
                lt_html, en_html, lv_html
            )

        return self._upload_html_to_prestashop(
            driver, product_code, lt_html, en_html, lv_html
        )

    def upload_to_prestashop_raw(
        self,
        driver,
        product_code: str,
        lt_html: str,
        en_html: str,
        lv_html: str,
        append_disclaimer: bool = False,
    ) -> bool:
        """Upload raw HTML content to PrestaShop"""

        self._log(
            "Uploading raw HTML to PrestaShop",
            product_code=product_code,
            append_disclaimer=append_disclaimer,
        )

        if append_disclaimer:
            lt_html, en_html, lv_html = self.append_disclaimer_if_missing(
                lt_html, en_html, lv_html
            )

        return self._upload_html_to_prestashop(
            driver, product_code, lt_html, en_html, lv_html
        )

    def _upload_html_to_prestashop(
        self,
        driver,
        product_code: str,
        lt_html: str,
        en_html: str,
        lv_html: str,
    ) -> bool:
        """Internal method to upload HTML to PrestaShop"""

        try:
            wait = WebDriverWait(driver, 10)

            try:
                current_url = driver.current_url
                if "#tab-step1" not in current_url:
                    driver.get(current_url.split("#")[0] + "#tab-step1")
                    time.sleep(1)
            except Exception:
                pass

            languages = [("lt", lt_html), ("en", en_html), ("lv", lv_html)]
            lang_id_map = {"lt": "2", "en": "1", "lv": "3"}

            for lang_code, html_content in languages:
                if not html_content:
                    continue

                self._log("Uploading language", lang=lang_code)

                language_dropdown = wait.until(
                    EC.element_to_be_clickable((By.ID, "form_switch_language"))
                )
                Select(language_dropdown).select_by_value(lang_code)
                time.sleep(1)

                iframe_id = f"form_step1_description_{lang_id_map[lang_code]}_ifr"
                wait.until(
                    EC.frame_to_be_available_and_switch_to_it((By.ID, iframe_id))
                )

                editor_body = wait.until(
                    EC.presence_of_element_located((By.ID, "tinymce"))
                )

                driver.execute_script(
                    "arguments[0].innerHTML = arguments[1];",
                    editor_body,
                    html_content,
                )

                driver.switch_to.default_content()
                time.sleep(0.5)

            self._log("HTML uploaded successfully", product_code=product_code)
            return True

        except Exception as e:
            import traceback

            self._log_error(
                "Failed to upload HTML", exception=e, product_code=product_code
            )
            # Error: traceback.format_exc() can be logged if needed

            try:
                driver.switch_to.default_content()
            except Exception:
                pass

            return False
