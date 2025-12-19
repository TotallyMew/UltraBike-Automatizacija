from Config.LoginConfig.LoginHandler import LoginHandler
from Config.LoginConfig.CredentialManager import CredentialManager
from uploaderFactory import getUploaderClass
from Utilities.ProductNavigationHandler import ProductNavigationHandler
from secondaryInput import process_codes_from_excel
from Config.BrowserConfig.BrowserManager import BrowserManager
from Config.Settings.SettingsManager import SettingsManager
from Utilities.FolderCreator import FolderCreator
from Utilities.SettingsMenu import SettingsMenu
from Utilities.Logger import Logger
from Utilities.ErrorManager import ErrorManager

def main():
    # The original CLI flow has been removed. Use GUI entrypoints in GUI/ or GUI_Qt/.

if __name__ == "__main__":
    # CLI entrypoint removed. Start the GUI via the GUI/ or GUI_Qt/ entrypoints.