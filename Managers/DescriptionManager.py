"""
Managers/DescriptionManager.py
Handles saved description CRUD and reusable description content preparation.
"""

# Standard library
from datetime import datetime

from Utilities.ErrorManager import ErrorManager


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
        self,
        name: str,
        description_lt: str,
        description_en: str,
        description_lv: str,
        original_name: str | None = None,
        folder: str = "",
    ) -> bool:
        """Save or update description in database"""
        self._log("Saving description", name=name, original_name=original_name, folder=folder)

        try:
            cursor = self.db.conn.cursor()

            if folder:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO description_folders (name, updated_at)
                    VALUES (?, ?)
                    """,
                    (folder, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                )

            effective_original_name = original_name or name

            if effective_original_name != name:
                name_conflict = cursor.execute(
                    "SELECT id FROM descriptions WHERE name = ?", (name,)
                ).fetchone()
                if name_conflict:
                    self._log("Description rename conflict", target_name=name)
                    return False

                renamed = cursor.execute(
                    "SELECT id FROM descriptions WHERE name = ?", (effective_original_name,)
                ).fetchone()
                if renamed:
                    cursor.execute(
                        """
                        UPDATE descriptions
                        SET name = ?, folder = ?, description_lt = ?, description_en = ?, description_lv = ?,
                            updated_at = ?
                        WHERE name = ?
                        """,
                        (
                            name,
                            folder,
                            description_lt,
                            description_en,
                            description_lv,
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            effective_original_name,
                        ),
                    )
                    self.db.conn.commit()
                    self._log("Description renamed and updated", from_name=effective_original_name, to_name=name)
                    return True

            existing = cursor.execute(
                "SELECT id FROM descriptions WHERE name = ?", (name,)
            ).fetchone()

            if existing:
                cursor.execute(
                    """
                    UPDATE descriptions
                    SET folder = ?, description_lt = ?, description_en = ?, description_lv = ?,
                        updated_at = ?
                    WHERE name = ?
                    """,
                    (
                        folder,
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
                    (name, folder, description_lt, description_en, description_lv)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (name, folder, description_lt, description_en, description_lv),
                )
                self._log("Description created", name=name)

            self.db.conn.commit()
            return True

        except Exception as e:
            self._log_error("Failed to save description", exception=e, name=name)
            return False

    def list_folders(self) -> list[str]:
        """Return all saved description folders sorted by name."""
        try:
            cursor = self.db.conn.cursor()
            results = cursor.execute(
                """
                SELECT name
                FROM description_folders
                ORDER BY name COLLATE NOCASE ASC
                """
            ).fetchall()
            return [r["name"] for r in results if (r["name"] or "").strip()]
        except Exception as e:
            self._log_error("Failed to list folders", exception=e)
            return []

    def create_folder(self, folder_name: str) -> bool:
        """Create a reusable folder for grouping descriptions."""
        name = (folder_name or "").strip()
        if not name:
            return False

        try:
            cursor = self.db.conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO description_folders (name, updated_at)
                VALUES (?, ?)
                """,
                (name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
            self.db.conn.commit()
            return True
        except Exception as e:
            self._log_error("Failed to create folder", exception=e, folder_name=name)
            return False

    def load_description(self, name: str) -> dict | None:
        """Load description from database"""
        self._log("Loading description", name=name)

        try:
            cursor = self.db.conn.cursor()
            result = cursor.execute(
                """
                SELECT name, COALESCE(folder, '') AS folder, description_lt, description_en, description_lv,
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
                "folder": result["folder"] or "",
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
                SELECT name, COALESCE(folder, '') AS folder, updated_at
                FROM descriptions
                ORDER BY folder COLLATE NOCASE ASC, name COLLATE NOCASE ASC
                """
            ).fetchall()

            return [
                {
                    "name": r["name"],
                    "folder": r["folder"] or "",
                    "updated_at": r["updated_at"],
                }
                for r in results
            ]

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

    def prepare_description(
        self,
        name: str,
        *,
        append_disclaimer: bool = False,
        only_lt: bool = False,
    ) -> dict[str, str] | None:
        """Return saved HTML keyed by PIMBO locale, without browser interaction."""
        desc = self.load_description(name)
        if not desc:
            self._log_error("Description not found", name=name)
            return None
        return self.prepare_raw_description(
            desc["description_lt"],
            desc["description_en"],
            desc["description_lv"],
            append_disclaimer=append_disclaimer,
            only_lt=only_lt,
        )

    def prepare_raw_description(
        self,
        lt_html: str,
        en_html: str,
        lv_html: str = "",
        *,
        append_disclaimer: bool = False,
        only_lt: bool = False,
    ) -> dict[str, str]:
        """Prepare raw HTML keyed by locale; PIMBO writes belong to its editor."""
        if append_disclaimer:
            lt_html, en_html, lv_html = self.append_disclaimer_if_missing(
                lt_html, en_html, lv_html
            )
        prepared = {"lt": lt_html or ""}
        if not only_lt:
            prepared.update({"en": en_html or "", "lv": lv_html or ""})
        return {locale: value for locale, value in prepared.items() if value.strip()}
