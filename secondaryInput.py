
import openpyxl

def process_codes_from_excel(file_path, sheet_name, uploader_class, driver, brand):
    workbook = openpyxl.load_workbook(file_path)
    sheet = workbook[sheet_name]
    for row in sheet.iter_rows(min_row=1, values_only=True):
        ultraBikeCode = row[1]
        bicycleUrlOrCode = row[2]

        if not ultraBikeCode or not bicycleUrlOrCode:
            continue

        uploader = uploader_class(driver, brand, ultraBikeCode=ultraBikeCode, bicycleUrlOrCode=bicycleUrlOrCode)
        result = uploader.run()
        # Results can be collected or handled by the caller (GUI, etc.)
