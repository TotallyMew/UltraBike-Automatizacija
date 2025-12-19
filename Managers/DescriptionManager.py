"""
Managers/DescriptionManager.py
Handles description CRUD operations and PrestaShop upload
"""

import time
from datetime import datetime
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
