import time
from selenium.webdriver.common.by import By

class WindowManager:
    @staticmethod
    def resize_window(driver, element_id, max_width, max_height):
        try:
            element = driver.find_element(By.ID, element_id)
            element_size = element.size
            current_width = element_size['width']
            current_height = element_size['height']

            window_size = driver.get_window_size()
            window_width = window_size['width']
            window_height = window_size['height']

            if current_width < max_width or current_height < max_height:
                new_width = int(window_width * (max_width / current_width)) if current_width > max_width else window_width
                new_height = int(window_height * (max_height / current_height)) if current_height > max_height else window_height

                driver.set_window_size(new_width, new_height)
                time.sleep(1)

                # Verify size after resizing
                element_size = element.size
        except Exception as e:
            from Utilities.ErrorManager import ErrorManager
            ErrorManager.show_error("UNEXPECTED_ERROR", error=str(e))
