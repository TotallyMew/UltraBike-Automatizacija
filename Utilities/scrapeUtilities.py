from distutils.command import upload
import re
import os
import json
import time
import random
import string
import urllib.parse
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from pywinauto.application import Application
from pywinauto.keyboard import send_keys

from Config.config import settings, resource_path, resizeWindow
import urllib3
import certifi
from urllib.parse import urlparse, urljoin



def is_valid_url(url):
    # Regex to validate a basic URL format
    regex = re.compile(
        r"^(https?://)?"  # http:// or https://
        r"([0-9A-Za-z_!~*\'().&=+$%-]+:)*"  # username:password (optional)
        r"([0-9A-Za-z_!~*\'().&=+$%-]+@)?"  # hostname@
        r"(([0-9]{1,3}\.){3}[0-9]{1,3}"  # IP address
        r"|"  # or
        r"([0-9A-Za-z_!~*\'()-]+\.)*"  # domain name
        r"([A-Za-z]{2,6}))"  # top level domain
        r"(:[0-9]{1,4})?"  # port (optional)
        r"(/+[0-9A-Za-z_!~*\'().;?:@&=+$,%#-]*)*$",  # path
        re.IGNORECASE,
    )
    return re.match(regex, url) is not None


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


def getURL(brandName):
    while True:
        url = input("Įveskite "+brandName.title()+" url: ")
        if not is_valid_url(url):
            print("Neteisingas URL formatas. Prašome įvesti tinkamą URL.")
        elif not is_website_accessible(url):
            print(
                "Svetainė nepasiekiama. Prašome patikrinti URL arba jūsų interneto ryšį."
            )
        else:
            return url



def loadTranslations(translation_file):
    translations = {}
    with open(translation_file, "r", encoding="utf-8") as file:
        for line in file:
            parts = line.split(":", 1)
            if len(parts) == 2:
                key = parts[0].strip().title()
                value = parts[1].strip()
                translations[key] = value
    return translations


def loadValueTranslations(translation_file):
    value_translations = {}
    with open(translation_file, "r", encoding="utf-8") as file:
        for line in file:
            parts = line.strip().split(":", 1)
            if len(parts) == 2:
                original_value = parts[0].strip()
                translated_value = parts[1].strip()
                value_translations[original_value] = translated_value
    return value_translations


def verstTikPirmaZodi(value, value_translations):
    value_parts = value.split()
    if not value_parts:
        return value

    first_word = value_parts[0].upper()
    if first_word in (
        "ALUMINIUM",
        "OK.",
        "CARBON",
        "ALIUMINIS",
        "APIE",
        "STEEL",
        "PLIENINIS",
        "STAL",
        "WITH SHOCK ABSORBER",
        "SU AMORTIZATORIUMI"
    ):  # pridet zodzius kuriuos kai verciam turi but isversti tik pradzioj, kad KROSS ALUMINIUM ... liktu aluminium, bet jeigu zodis butu pries KROSS tada isverstu
        value_parts[0] = value_translations.get(first_word, value_parts[0])

    return " ".join(value_parts)


def loadAngluVertimas(translation_file):
    english_translations = {}
    with open(translation_file, "r", encoding="utf-8") as file:
        for line in file:
            parts = line.strip().split(":", 1)
            if len(parts) == 2:
                lithuanian_value = parts[0].strip()
                english_value = parts[1].strip()
                english_translations[lithuanian_value] = english_value
    return english_translations


def versti_I_Anglu(input_file, output_file, angluVertimoFailas):
    english_translations = loadAngluVertimas(angluVertimoFailas)

    with open(input_file, "r", encoding="utf-8") as infile, open(
        output_file, "w", encoding="utf-8"
    ) as outfile:
        for line in infile:
            if line.strip():
                try:
                    key, lithuanian_value = line.strip().split(": ", 1)
                    english_value = english_translations.get(
                        lithuanian_value, lithuanian_value
                    )
                    english_value = verstTikPirmaZodi(english_value, english_translations)
                    outfile.write(f"{key}: {english_value}\n")
                except:
                    print("Klaida verciant i anglu kalba")
            else:
                outfile.write("\n")


# I table viska sumetam
def nuskaitytIsverstasFailasLietuviu(file_path):
    tables = []
    table_data = {}

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            for line in file:
                if line.strip() == "":  # Check for empty line
                    if table_data:
                        tables.append(table_data)  # Add current table data
                        table_data = {}  # Reset for the next table
                    continue
                
                try:
                    key, value = line.strip().split(": ", 1)  # Expect a key-value pair
                    table_data[key] = value
                except ValueError:
                    print(f"Warning: Line is not in 'key: value' format: {line.strip()}")
        
        if table_data:  # Check if there's any remaining data to add
            tables.append(table_data)

    except FileNotFoundError:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        # Create the file
        with open(file_path, "w", encoding="utf-8") as file:
            file.write("")
        return nuskaitytIsverstasFailasAnglu(file_path)
    except Exception as e:
        print(f"An error occurred: {e}")

    return tables



def nuskaitytIsverstasFailasAnglu(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        tables_eng = []
        table_data_eng = {}

        for line in file:
            if line.strip() == "":
                if table_data_eng:
                    tables_eng.append(table_data_eng)
                    table_data_eng = {}
                continue

            key, value = line.strip().split(": ", 1)
            table_data_eng[key] = value

        if table_data_eng:
            tables_eng.append(table_data_eng)

        return tables_eng


#Viska kas susije su nuotraukom perkelt i atskila .py faila    
def pasalintiNeleistinusSimbolius(name):
    return re.sub(r'[<>:"/\\|?*]', '', name)


def generate_random_string(length=8): #Kartais Kross tinklapy nuotrauku linkai turi daug neleidziamu simboliu, todel nuotrauku pavadinimams tiesiog sukuriam random pavadinimus
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def siustiNuotraukasKROSS(url, driver):
    download_path = sukonstruotiDirectory(driver)

    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Klaida gaunant puslapio turinį: {e}")

    soup = BeautifulSoup(response.content, 'html.parser')
    image_elements = soup.select('a.orbitvu-gallery-item-link')

    if not image_elements:
        raise ValueError("Nuotraukos nerastos pateiktame tinklapyje")

    for element in image_elements:
        img_url = element.get('data-big_src')
        if not img_url:
            continue
        
        img_url = urljoin(url, img_url)  # Ensures absolute URL
        img_name = os.path.basename(urlparse(img_url).path)

        if img_name.lower() == 'view.png': #360 modelis
            continue

        try:
            img_response = requests.get(img_url)
            img_response.raise_for_status()
        except requests.RequestException as e:
            print(f"Klaida siunčiant nuotrauką {img_url}: {e}")
            continue

        img_path = os.path.join(download_path, img_name)
        with open(img_path, 'wb') as img_file:
            img_file.write(img_response.content)

    print('Nuotraukos parsiųstos.')

def sukonstruotiDirectory(driver): 
    global settings
    input_element = driver.find_element(By.ID, 'form_step1_name_2')
    value = input_element.get_attribute('value')
    base_directory = resource_path(settings[1])
    sanitized_value = pasalintiNeleistinusSimbolius(value)
    download_directory = os.path.join(base_directory, sanitized_value)
    os.makedirs(download_directory, exist_ok=True)
    return download_directory

def sukeltiNuotraukasKROSS(driver):
    resizeWindow(driver, 'add_feature_button', 160.07, 39.14)
    try:
        element = driver.find_element(By.CLASS_NAME, 'dz-preview.disabled.openfilemanager.dz-clickable')
        if element.is_displayed() and element.is_enabled():
            print("Nuotraukų jau yra sukelta, naujos nuotraukos nebus keliamos. Norint kelti nuotraukas ištrinkite esamas")
            return
        else:
            print("Ruošiamasi kelti nuotraukas")
    except NoSuchElementException:
        print('Element not found, continuing with regular code')

    try:
        download_path = sukonstruotiDirectory(driver)
        upload_button = driver.find_element(By.ID, 'product-images-dropzone')
        driver.execute_script("arguments[0].scrollIntoView();", upload_button)
        upload_button.click()
        time.sleep(2)

        app = Application().connect(title_re='Open') 
        dialog = app.window(title_re='Open') 

        dialog['Edit'].set_text(download_path) 
        send_keys("{ENTER}")
        time.sleep(1) 

        tree_view = dialog.TreeView
        tree_view.set_focus()

       
        send_keys('^a') 
        time.sleep(1)
        send_keys('{ENTER}')

        print("Nuotraukos sukeltos.")
    except Exception as e:
        print(f"Error: {e}")