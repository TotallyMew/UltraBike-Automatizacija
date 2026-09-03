"""Deterministic KROSS bicycle specification preparation.

KROSS product names contain several reliable PIMBO specification values.  The
public KROSS specification table is Polish, while PIMBO's Dviračiai field names
are Lithuanian and their values must be English.  This module keeps the parsing
and translation rules independent from Selenium so they can be tested without
opening a product.
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or "")).replace("\xa0", " ")).strip()


def _fold(value: Any) -> str:
    normalized = unicodedata.normalize(
        "NFKD",
        _clean(value).casefold().translate(str.maketrans({"ł": "l"})),
    )
    return re.sub(r"\s+", " ", "".join(
        character for character in normalized
        if not unicodedata.combining(character)
    )).strip()


@dataclass(frozen=True)
class KrossNameSpecifications:
    model: str = ""
    color: str = ""
    finish: str = ""
    wheel_size: str = ""


@dataclass(frozen=True)
class KrossSpecificationPlan:
    """Values to overwrite directly plus the safe source passed to MagicAI."""

    values: tuple[tuple[str, str], ...]
    magic_ai_source: str


_FINISHES = {
    "glossy": "Glossy",
    "gloss": "Gloss",
    "matte": "Matte",
    "matt": "Matte",
    "mat": "Matte",
    "polysk": "Glossy",
    "matowy": "Matte",
}


def parse_kross_product_name(value: str) -> KrossNameSpecifications:
    """Extract the stable bicycle fields from a PIMBO KROSS product name.

    Delimiters require surrounding whitespace so a colour such as ``Blue/Red``
    remains one value.
    """

    name = _clean(value)
    parts = re.split(r"\s+/\s+", name, maxsplit=2)
    model = parts[0] if parts else ""
    model = re.sub(r"(?i)(?:^|\s+)MY\s*[-–]?\s*\d{2,4}\b", " ", model)
    model = _clean(model)

    color = ""
    finish = ""
    if len(parts) >= 2:
        color_and_finish = _clean(parts[1])
        match = re.match(
            r"^(?P<color>.+?)\s+(?P<finish>glossy|gloss|matte|matt|mat|połysk|matowy)$",
            color_and_finish,
            flags=re.IGNORECASE,
        )
        if match:
            color = _clean(match.group("color"))
            finish = _FINISHES.get(_fold(match.group("finish")), _clean(match.group("finish")))
        else:
            color = color_and_finish

    wheel_matches = re.findall(
        r"(?<!\d)(\d{2}(?:[.,]\d+)?)\s*(?:\"|″|&quot;|inches?)",
        name,
        flags=re.IGNORECASE,
    )
    wheel_size = f'{wheel_matches[-1]}"' if wheel_matches else ""
    return KrossNameSpecifications(model, color, finish, wheel_size)


_SIZE_ORDER = {
    "XXXS": 0,
    "3XS": 0,
    "XXS": 1,
    "2XS": 1,
    "XS": 2,
    "S": 3,
    "M": 4,
    "L": 5,
    "XL": 6,
    "XXL": 7,
    "2XL": 7,
    "XXXL": 8,
    "3XL": 8,
    "4XL": 9,
    "5XL": 10,
}


def sort_kross_frame_sizes(values: Iterable[str]) -> tuple[str, ...]:
    """Deduplicate and sort frame sizes from XXXS through XXXL, then numbers."""

    unique: dict[str, str] = {}
    for value in values:
        size = _clean(value)
        if size:
            unique.setdefault(size.casefold(), size)

    def key(size: str) -> tuple[int, float, str]:
        upper = size.upper()
        if upper in _SIZE_ORDER:
            return 0, float(_SIZE_ORDER[upper]), ""
        numeric = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(?:CM|\"|″)?", upper)
        if numeric:
            return 1, float(numeric.group(1).replace(",", ".")), ""
        return 2, 0.0, size.casefold()

    return tuple(sorted(unique.values(), key=key))


def parse_kross_specification_rows(value: str) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = []
    for raw_line in str(value or "").splitlines():
        if ":" not in raw_line:
            continue
        label, raw_value = raw_line.split(":", 1)
        label = _clean(label)
        row_value = _clean(raw_value)
        if label and row_value:
            rows.append((label, row_value))
    return tuple(rows)


# These names mirror the established Assets/Translations PL→LT component map.
# Overrides requested specifically for this workflow are intentionally explicit.
_LABEL_TRANSLATIONS = {
    "material ramy": "Rėmo medžiaga",
    "rama": "Rėmo medžiaga",
    "frame": "Rėmo medžiaga",
    "amortyzator / widelec": "Šakė",
    "widelec": "Šakė",
    "skok widelca": "Šakės eiga",
    "skok amortyzatora przod": "Šakės eiga",
    "tylny amortyzator": "Galinis amortizatorius",
    "amortyzator tyl": "Galinis amortizatorius",
    "skok tylnego amortyzatora": "Galinio amortizatoriaus eiga",
    "skok amortyzatora tyl": "Galinio amortizatoriaus eiga",
    "wykonczenie lakieru": "Lako užbaigimas",
    "kolor ramy": "Pagrindinė spalva",
    "kolor bazowy": "Pagrindinė spalva",
    "przerzutka przod": "Priekinis pavarų perjungėjas",
    "przerzutka tyl": "Galinis pavarų perjungėjas",
    "manetki": "Pavarų rankenėlės",
    "koronki": "Priekiniai dantračiai",
    "korba": "Švaistikliai",
    "kaseta / wolnobieg": "Galinis žvaigždžių blokas",
    "zakres kasety/wolnobiegu": "Galinio žvaigždžių bloko diapazonas",
    "zakres kasety": "Galinio žvaigždžių bloko diapazonas",
    "ilosc przelozen": "Pavarų skaičius",
    "ilosc biegow": "Pavarų skaičius",
    "suport": "Centrinės ašies guolis",
    "wklad suportu": "Centrinės ašies guolis",
    "lancuch": "Grandinė",
    "piasta przod": "Priekinė stebulė",
    "piasta tyl": "Galinė stebulė",
    "obrecze": "Ratlankiai",
    "opony": "Padangos",
    "hamulec przod": "Priekiniai stabdžiai",
    "hamulec tyl": "Galiniai stabdžiai",
    "dzwignie hamulca": "Stabdžių rankenėlės",
    "tarcze hamulcowe": "Maksimalus stabdžių disko dydis",
    "tarcze hamulcowe tyl": "Maksimalus stabdžių disko dydis",
    "tarcza hamulcowa przod": "Maksimalus stabdžių disko dydis",
    "tarcza hamulcowa tyl": "Maksimalus stabdžių disko dydis",
    "kierownica": "Vairas",
    "wspornik kierownicy": "Vairo iškyša",
    "siodlo": "Balnelis",
    "wspornik siodla": "Balnakotis",
    "stery": "Vairo kolonėlės guoliai",
    "chwyty": "Vairo rankenėlės / juosta",
    "pedaly": "Pedalai",
    "silnik": "Variklis",
    "bateria": "Akumuliatorius",
    "wyswietlacz": "Ekranas",
    "waga": "Dviračio svoris (kg)",
    "waga [kg]": "Dviračio svoris (kg)",
    "dlugosc": "Ilgis",
    "kolor": "Pagrindinė spalva",
    "material": "Medžiaga",
    "maksymalna szerokosc opony (mm)": "Didžiausias padangos plotis (mm)",
    "rozmiar kola": "Ratų dydis",
    "moment obrotowy silnika": "Variklio sukimo momentas",
    "moc silnika": "Variklio galia",
    "umiejscowienie silnika": "Variklio vieta",
    "pojemnosc baterii": "Akumuliatoriaus talpa",
    "umiejscowienie baterii": "Akumuliatoriaus vieta",
    "maksymalny zasieg (km)": "Didžiausias nuvažiuojamas atstumas (km)",
    "napiecie silnika (v)": "Variklio įtampa (V)",
    "ladowarka (napiecie/natezenie)": "Įkroviklis (įtampa / srovė)",
    "czas ladowania (h)": "Įkrovimo laikas (val.)",
    "tryb wspomagania": "Pagalbos režimas",
    "walk assist": "Ėjimo pagalba",
    "usb port": "USB jungtis",
    "zamek baterii": "Akumuliatoriaus užraktas",
    "maksymalna predkosc wspomagania (km/h)": "Didžiausias pagalbinio važiavimo greitis (km/h)",
    "numer certyfikatu": "Sertifikato numeris",
}


_VALUE_TRANSLATIONS = {
    "ALUMINIUM": "ALUMINIUM",
    "CARBON": "CARBON",
    "STAL": "STEEL",
    "TWORZYWO": "PLASTIC",
    "TWORZYWO/STAL": "PLASTIC/STEEL",
    "ALUMINIUM/STAL": "ALUMINIUM/STEEL",
    "ALUMINIUM/TWORZYWO": "ALUMINIUM/PLASTIC",
    "POŁYSK": "GLOSS",
    "MATOWY": "MATTE",
    "MAT": "MATTE",
    "TARCZOWY MECHANICZNY": "MECHANICAL DISC",
    "TAK": "YES",
    "NIE": "NO",
    "BRAK": "NONE",
    "CENTRALNY": "CENTRAL",
    "ZINTEGROWANA": "INTEGRATED",
    "TYLNE KOŁO": "REAR WHEEL",
    "BAGAŻNIK": "REAR RACK",
    "CZARNY": "BLACK",
    "CZARNA": "BLACK",
    "BIAŁY": "WHITE",
    "WHITE": "WHITE",
    "SZARY": "GREY",
    "CIEMNY SZARY": "DARK GREY",
    "SREBRNY": "SILVER",
    "GRANATOWY": "NAVY BLUE",
    "NIEBIESKI": "BLUE",
    "BŁĘKITNY": "LIGHT BLUE",
    "CZERWONY": "RED",
    "ZIELONY": "GREEN",
    "ZIELONOSZARY": "GREEN GREY",
    "ŻÓŁTY": "YELLOW",
    "RÓŻOWY": "PINK",
    "FIOLETOWY": "PURPLE",
    "BRĄZOWY": "BROWN",
    "ZŁOTY": "GOLD",
    "GRAFITOWY": "GRAPHITE",
    "TURKUSOWY": "TURQUOISE",
    "BORDOWY": "BURGUNDY",
    "PERŁOWY": "PEARL",
    "RUBINOWY": "RUBY",
    "POMARAŃCZOWY": "ORANGE",
    "MIEDZIANY": "COPPER",
    "LIMONKOWY": "LIME GREEN",
    "KORALOWY": "CORAL",
    "BEŻOWY": "BEIGE",
    "SELEDYNOWY": "CELADON",
    "MORSKI": "SEA BLUE",
}


_BAD_PEDAL_VALUES = {
    "brak",
    "brak pedalow",
    "brak pedalow w zestawie",
    "nie",
}


def _lookup_translation(
    translator: Any,
    value: str,
    source_language: str,
    target_language: str,
) -> str:
    if translator is None:
        return ""
    try:
        translated = _clean(
            translator.get_translation(value.upper(), source_language, target_language)
        )
    except Exception:
        return ""
    return "" if not translated or translated.casefold() == value.casefold() else translated


def translate_kross_specification_value(value: str, translator: Any = None) -> str:
    """Translate known Polish material/property words without touching model names."""

    source = _clean(value)
    if not source:
        return ""
    exact = _lookup_translation(translator, source, "PL", "EN")
    if not exact:
        lithuanian = _lookup_translation(translator, source, "PL", "LT")
        exact = (
            _lookup_translation(translator, lithuanian, "LT", "EN")
            if lithuanian
            else ""
        )
    if exact:
        return exact

    upper = source.upper()
    if upper in _VALUE_TRANSLATIONS:
        return _VALUE_TRANSLATIONS[upper]

    # Translate known words inside combined values such as "SZARY / ZIELONY"
    # and preserve vendor/model text around them.
    translated = source
    for polish, english in sorted(
        _VALUE_TRANSLATIONS.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if "/" in polish:
            continue
        translated = re.sub(
            rf"(?<![\w]){re.escape(polish)}(?![\w])",
            english,
            translated,
            flags=re.IGNORECASE,
        )
    translated = re.sub(r"(?i)^do\s+(?=\d)", "up to ", translated)
    translated = re.sub(r"(?i)^ok\.\s*", "approx. ", translated)
    translated = re.sub(
        r"(?i)^Spełnia normy UE dotyczące rowerów elektrycznych",
        "Meets EU standards for electric bicycles",
        translated,
    )
    return _clean(translated)


def _translated_label(label: str, translator: Any = None) -> str:
    folded = _fold(label)
    if folded in _LABEL_TRANSLATIONS:
        return _LABEL_TRANSLATIONS[folded]
    translated = _lookup_translation(translator, _clean(label), "PL", "LT")
    return translated if translated and translated.casefold() != _clean(label).casefold() else ""


def build_kross_specification_plan(
    product_name: str,
    variant_sizes: Iterable[str],
    specification_text: str,
    *,
    translator: Any = None,
) -> KrossSpecificationPlan:
    """Build authoritative PIMBO values and a value-translated MagicAI source."""

    direct_values: dict[str, str] = {}
    magic_ai_rows: list[str] = []
    for label, source_value in parse_kross_specification_rows(specification_text):
        target = _translated_label(label, translator)
        if _fold(label) == "pedaly" and _fold(source_value) in _BAD_PEDAL_VALUES:
            # Clear a stale PIMBO pedal value and keep the bad source away from
            # MagicAI, which otherwise correctly fills an empty field with it.
            direct_values["Pedalai"] = ""
            continue
        translated_value = translate_kross_specification_value(source_value, translator)
        magic_ai_rows.append(f"{label}: {translated_value}")
        if target:
            direct_values[target] = translated_value

    parsed_name = parse_kross_product_name(product_name)
    # These five fields are authoritative whenever this opt-in stage is run.
    # Empty extracted values intentionally clear stale PIMBO values.
    direct_values.update({
        "Modelis": parsed_name.model,
        "Spalva": parsed_name.color,
        "Lako užbaigimas": parsed_name.finish,
        "Ratų dydis": parsed_name.wheel_size,
    })
    sorted_sizes = sort_kross_frame_sizes(variant_sizes)
    if sorted_sizes:
        # Do not silently erase this field when a changed PIMBO Variants layout
        # cannot be read. The service reports the missing sizes as a warning.
        direct_values["Galimi rėmo dydžiai"] = ", ".join(sorted_sizes)
    return KrossSpecificationPlan(
        values=tuple(direct_values.items()),
        magic_ai_source="\n".join(magic_ai_rows),
    )
