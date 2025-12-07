class TranslationHandler:
    @staticmethod
    def load_translations(translation_file):
        translations = {}
        with open(translation_file, "r", encoding="utf-8") as file:  # FIXED
            for line in file:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    key = parts[0].strip().title()
                    value = parts[1].strip()
                    translations[key] = value
        return translations

    @staticmethod
    def load_value_translations(translation_file):
        value_translations = {}
        with open(translation_file, "r", encoding="utf-8") as file:  # FIXED: Changed from utf-8-sig
            for line in file:
                parts = line.strip().split(":", 1)
                if len(parts) == 2:
                    original_value = parts[0].strip().upper()
                    translated_value = parts[1].strip()
                    value_translations[original_value] = translated_value
        return value_translations

    @staticmethod
    def translate_first_word(value, value_translations):
        value_parts = value.split()
        if not value_parts:
            return value

        first_word = value_parts[0].upper()
        if first_word in (
            "ALUMINIUM", "ALIUMINIS",
            "OK.", "APIE",
            "CARBON", "ANGLIES PLUOŠTAS",
            "ALIUMINIS", "ALIUMINIS",
            "APIE", "APIE",
            "STEEL", "PLIENINIS",
            "PLIENINIS", "PLIENINIS",
            "STAL", "PLIENINIS",
            "WITH SHOCK ABSORBER", "SU AMORTIZATORIUMI",
            "SU AMORTIZATORIUMI", "SU AMORTIZATORIUMI",

            # Colors
            "CZARNY", "JUODA",
            "POŁYSK", "BLIZGUS",
            "MATOWY", "MATINIS",
            "ŻÓŁTY", "GELTONA",
            "SZARY", "PILKA",
            "CIEMNY", "TAMSIAI",
            "SREBRNY", "SIDABRINĖ",
            "GRANATOWY", "TAMSIAI MĖLYNA",
            "MIĘTOWY", "MĖTINĖ",
            "RÓŻOWY", "ROŽINĖ",
            "BIAŁY", "BALTA",
            "NIEBIESKI", "MĖLYNA",
            "CZERWONY", "RAUDONA",
            "FIOLETOWY", "VIOLETINĖ",
            "ZIELONY", "ŽALIA"
        ):
            value_parts[0] = value_translations.get(first_word, value_parts[0])
        return " ".join(value_parts)

    @staticmethod
    def translate_to_english(input_file, output_file, translation_file):
        english_translations = TranslationHandler.load_value_translations(translation_file)

        with open(input_file, "r", encoding="utf-8") as infile, \
             open(output_file, "w", encoding="utf-8") as outfile:
            for line in infile:
                if line.strip():
                    try:
                        key, lithuanian_value = line.strip().split(": ", 1)
                        english_value = english_translations.get(
                            lithuanian_value.upper(), lithuanian_value
                        )
                        english_value = TranslationHandler.translate_first_word(
                            english_value, english_translations
                        )
                        outfile.write(f"{key}: {english_value}\n")
                    except:
                        print("Klaida verciant i anglu kalba")
                else:
                    outfile.write("\n")