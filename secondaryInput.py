import openpyxl

def process_codes_from_excel(file_path, sheet_name, uploader_class, driver, brand):
    workbook = openpyxl.load_workbook(file_path)
    sheet = workbook[sheet_name]
    for row in sheet.iter_rows(min_row=1, values_only=True):
        ultraBikeCode = row[1]  # Column A
        bicycleUrlOrCode = row[2]  # Column B

        if not ultraBikeCode or not bicycleUrlOrCode:
            continue

        print(f"Processing ultraBikeCode: {ultraBikeCode}, bassoConfigCode: {bicycleUrlOrCode}")
        uploader = uploader_class(driver, brand, ultraBikeCode=ultraBikeCode, bicycleUrlOrCode=bicycleUrlOrCode)
        result = uploader.run()
        print(result)
        # while True:
        #     user_input = input("Tęsti su kita eilute? (y = taip, m = rankinis įvedimas, q = išeiti): ").strip().lower()
        #     if user_input == 'y':
        #         break
        #     elif user_input == 'm':
        #         print("-- Perjungta į rankinį įvedimą --")
        #         return "manual"
        #     elif user_input == 'q':
        #         return "quit"
        #     else:
        #         print("Netinkamas įvestis. Naudokite 'y', 'm', arba 'q'.")
