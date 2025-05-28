from Uploaders.TREK import TREK
from Uploaders.KROSS import KROSS
from Uploaders.Rondo import Rondo
from Uploaders.Pinarello import Pinarello
from Uploaders.Octane import Octane
from Uploaders.Rascal import Rascal
from Uploaders.Basso import Basso
from Uploaders.LeeCougan import LeeCougan
from Uploaders.KrossFromTxt import KROSSTXT

def getUploaderClass(brandName):
    name = brandName.strip().lower().replace(" ", "")
    return {
        "kross": KROSS,
        "le grand": KROSS,  # Alias handled here
        "rondo": Rondo,
        "pinarello": Pinarello,
        "octane": Octane,
        "rascal": Rascal,
        "basso": Basso,
        "leecougan":LeeCougan,
        "trek": TREK,
        "krosstxt": KROSSTXT
    }.get(name)

