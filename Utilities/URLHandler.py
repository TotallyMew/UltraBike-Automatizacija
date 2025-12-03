import re
import requests
import urllib3



class URLHandler:
    @staticmethod
    def is_valid_url(url):
        regex = re.compile(
            r"^(https?://)?"
            r"([0-9A-Za-z_!~*\'().&=+$%-]+:)*"
            r"([0-9A-Za-z_!~*\'().&=+$%-]+@)?"
            r"(([0-9]{1,3}\.){3}[0-9]{1,3}"
            r"|"
            r"([0-9A-Za-z_!~*\'()-]+\.)*"
            r"([A-Za-z]{2,6}))"
            r"(:[0-9]{1,4})?"
            r"(/+[0-9A-Za-z_!~*\'().;?:@&=+$,%#-]*)*$",
            re.IGNORECASE,
        )
        return re.match(regex, url) is not None

    @staticmethod
    def is_website_accessible(url):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        }
        try:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            response = requests.get(url, headers=headers, timeout=5, verify=False)
            return response.status_code == 200
        except requests.RequestException as e:
            print(f"Negalima pasiekti svetainės: {e}")
            return False

    @staticmethod
    def get_brand_url(brand_name):
        name = brand_name.strip().lower().replace(" ", "")
        while True:
            if name in ["leecougan", "basso"]:
                return input(f"Įveskite {brand_name.title()} kodą: ")
            else:
                url = input(f"Įveskite {brand_name.title()} url: ")
                if not URLHandler.is_valid_url(url):
                    print("Neteisingas URL formatas. Prašome įvesti tinkamą URL.")
                elif not URLHandler.is_website_accessible(url):
                    print("Svetainė nepasiekiama. Prašome patikrinti URL arba jūsų interneto ryšį.")
                else:
                    return url
