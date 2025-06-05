# scrapers/KROSSScraper.py
from Utilities.scrapeUtilities import (
    loadTranslations,
    loadValueTranslations,
    verstTikPirmaZodi,
)

internalCounter = 0

def scrapeAndTranslateToFileKROSSTXT(url, outputFile):
    global internalCounter

    """
    Store predefined KROSS LIFTIE 16" bike specifications instead of scraping
    """
    keyTranslations = loadTranslations("Assets/Translations\\vertimasDetalesENG-LT.txt")
    valueTranslations = loadValueTranslations("Assets/Translations\\vertimasSavybesENG-LT.txt")
    
    # Static bike specifications from KROSS LIFTIE 16"
    bikeData = {
        "GEARS": "1",
        "FRAME": "ALUMINIUM LITE",
        "FORK": "ALUMINIUM",
        "FRONT BRAKE": "V-BRAKE",
        "REAR BRAKE": "V-BRAKE",
        "BRAKE LEVERS": "TWORZYWO",
        "CRANKS": "ALUMINIUM",
        "TEETHS": "25T/89MM",
        "BOTTOM BRACKET": "FP-MM",
        "CHAIN": "YBN",
        "CASSETTE/FREEWHEEL": "SINGLE",
        "CASSETTE/FREEWHEEL RANGE": "15T",
        "FRONT HUB": "ALUMINIUM",
        "REAR HUB": "ALUMINIUM",
        "RIMS": "ALUMINIUM",
        "TIRES": "VEE RAIL 14x1.5",
        "HANDLEBAR": "ALUMINIUM 500/22.2",
        "STEM": "ALUMINIUM 22.2 60MM",
        "SEATPOST": "ALUMINIUM",
        "SEAT": "JOY 16x60MM",
        "HEADSET": "1\" AHEAD",
        "SADDLE": "KROSS",
        "GRIPS": "KRATON",
        "PEDALS": "COMPOSITE",
    }
    
    allData = []
    uniqueKeys = set()
    
    try:
        # Process the static data
        tableData = {}
        
        for key, value in bikeData.items():
            # Skip empty values (marked with "-")
            if value == "-":
                continue
                
            # Format key to title case
            formattedKey = key.replace("_", " ").title()
            
            # Apply translations
            translatedKey = keyTranslations.get(formattedKey, formattedKey)
            translatedValue = valueTranslations.get(value, value)
            
            translatedValue = verstTikPirmaZodi(translatedValue, valueTranslations)

            tableData[translatedKey] = translatedValue
            uniqueKeys.add(translatedKey)
        
        allData.append(tableData)
        

        if(internalCounter ==0):
            # Add default colors (can be customized as needed)
            mainColor = "YELLOW"  # Default main color, can be modified
            translated = verstTikPirmaZodi(valueTranslations.get(mainColor, mainColor), valueTranslations)
            allData[0]["Pagrindinė spalva"] = translated
            uniqueKeys.add("Pagrindinė spalva")
            internalCounter+=1
        elif(internalCounter==1):
                        # Add default colors (can be customized as needed)
            mainColor = "MINT"  # Default main color, can be modified
            translated = verstTikPirmaZodi(valueTranslations.get(mainColor, mainColor), valueTranslations)
            allData[0]["Pagrindinė spalva"] = translated
            uniqueKeys.add("Pagrindinė spalva")
            internalCounter+=2
        else:
                        # Add default colors (can be customized as needed)
            mainColor = "WHITE"  # Default main color, can be modified
            translated = verstTikPirmaZodi(valueTranslations.get(mainColor, mainColor), valueTranslations)
            allData[0]["Pagrindinė spalva"] = translated
            uniqueKeys.add("Pagrindinė spalva")
        
        # Write result to file
        with open(outputFile, "w", encoding="utf-8") as f:
            for table in allData:
                for key, val in table.items():
                    f.write(f"{key}: {val}\n")
                f.write("\n")
        
        return f"Total unique keys: {len(uniqueKeys)}"
        
    except Exception as e:
        return f"Klaida apdorojant KROSS duomenis: {e}"
