import json

class CredentialManager:

    
    def __init__(self):
        self.login_path = "Config/LoginConfig\\loginInfo.json"
    
    def save_credentials(self, email: str, password: str) -> None:

        credentials = self.load_credentials()
        credentials[email] = password
        
        with open(self.login_path, 'w') as f:
            json.dump(credentials, f)
    
    def load_credentials(self) -> dict:

        try:
            with open(self.login_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def get_saved_credentials(self) -> tuple:

        credentials = self.load_credentials()
        
        if not credentials:
            return None, None
            
        if len(credentials) > 1:
            for i, email in enumerate(credentials.keys()):
                print(f"{i + 1}. {email}")
            choice = int(input("Pasirinkite paskyrą (įveskite skaičių): ")) - 1
            email = list(credentials.keys())[choice]
            return email, credentials[email]
        else:
            email = next(iter(credentials))
            return email, credentials[email]
