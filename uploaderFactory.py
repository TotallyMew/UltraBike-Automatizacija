# uploaderFactory.py

from Uploaders.KROSS import KROSS
# from uploaders.Rondo import Rondo
# from uploaders.Pinarello import Pinarello
# from uploaders.Octane import Octane
# from uploaders.Rascal import Rascal

def getUploaderClass(brandName):
    name = brandName.strip().lower()
    return {
        "kross": KROSS,
        "le grand": KROSS,  # Alias handled here
        # "rondo": Rondo,
        # "pinarello": Pinarello,
        # "octane": Octane,
        # "rascal": Rascal
    }.get(name)

