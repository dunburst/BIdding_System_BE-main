import sys
import os
import time
import logging
import io
import shutil
import re
<<<<<<< HEAD
=======
import mimetypes  # Thư viện để nhận diện file
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text 

# Import kết nối và model
from database import SessionLocal, engine
import models

<<<<<<< HEAD
=======
# Import MinIO Client
from minio_client import MinIOHandler

>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
# Selenium
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger   

# Setup Logging
try:
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except:
    pass

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PC1_Bot")

class MuasamcongDBBot:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.download_dir = os.path.join(self.base_dir, "downloads")
        self.driver_path = os.path.join(self.base_dir, "msedgedriver.exe")
        
<<<<<<< HEAD
=======
        # --- Khởi tạo MinIO ---
        self.minio = MinIOHandler()

>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)
            
        try:
            self.db: Session = SessionLocal()
            self.db.execute(text("SELECT 1")) 
            logger.info("-> Kết nối Database thành công!")
        except Exception as e:
            logger.error(f"-> LỖI KẾT NỐI DATABASE: {e}")
            sys.exit(1) 
        
        self.edge_options = Options()
        self.edge_options.add_argument("--window-size=1920,1080")
        self.edge_options.add_argument("--disable-notifications")
        self.edge_options.add_argument("--disable-popup-blocking")
        
        self.prefs = {
            "download.default_directory": self.download_dir,
            "download.prompt_for_download": False,
            "plugins.always_open_pdf_externally": True
        }
        self.edge_options.add_experimental_option("prefs", self.prefs)

    def start_driver(self):
        if not os.path.exists(self.driver_path):
            logger.error("Không tìm thấy msedgedriver.exe")
            return None
        return webdriver.Edge(service=Service(self.driver_path), options=self.edge_options)

    # ---------------------------------------------------------
    # HELPER FUNCTIONS
    # ---------------------------------------------------------
    def parse_date(self, date_str):
        if not date_str: return None
        date_str = date_str.strip()
        try:
            return datetime.strptime(date_str, "%d/%m/%Y %H:%M")
        except:
            try:
                return datetime.strptime(date_str, "%d/%m/%Y")
            except:
                return None

    def clean_money(self, money_str):
        if not money_str: return 0.0
<<<<<<< HEAD
        
        # Chuyển về chữ thường để so sánh
        s = str(money_str).lower().strip()
        
        # Nếu gặp chữ "miễn phí" hoặc "không" -> Trả về 0
        if "Miễn phí" in s or "Không" in s:
            return 0.0
            
        # Nếu là số sẵn thì trả về luôn
        if isinstance(money_str, (int, float)): return float(money_str)

        # Xóa hết ký tự không phải số (giữ lại số và dấu chấm thập phân nếu có)
        # Lưu ý: Nếu tiền Việt dùng dấu chấm (10.000) thì phải xóa dấu chấm trước
        clean_str = re.sub(r'[^\d]', '', s)
        
=======
        s = str(money_str).lower().strip()
        if "miễn phí" in s or "không" in s:
            return 0.0
        if isinstance(money_str, (int, float)): return float(money_str)
        clean_str = re.sub(r'[^\d]', '', s)
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
        try:
            return float(clean_str)
        except:
            return 0.0
        
    def get_info_by_label(self, driver, label_patterns):
<<<<<<< HEAD
        """
        Tìm text dựa trên nhãn. 
        label_patterns: Có thể là chuỗi (str) hoặc danh sách chuỗi (list).
        """
        if isinstance(label_patterns, str):
            label_patterns = [label_patterns]
            
        for label in label_patterns:
            # XPath thông minh: 
            # 1. Tìm div chứa text nhãn
            # 2. Nhảy lên cha là row/col
            # 3. Tìm div chứa giá trị bên cạnh (following-sibling)
            xpaths = [
                f"//div[contains(text(), '{label}')]/following-sibling::div",
                f"//div[contains(@class,'row')]//div[contains(text(), '{label}')]/../following-sibling::div",
                f"//td[contains(text(), '{label}')]/following-sibling::td", # Trường hợp bảng
                f"//*[contains(text(), '{label}')]/parent::*/following-sibling::*"
            ]
            
=======
        if isinstance(label_patterns, str):
            label_patterns = [label_patterns]
        for label in label_patterns:
            xpaths = [
                f"//div[contains(text(), '{label}')]/following-sibling::div",
                f"//div[contains(@class,'row')]//div[contains(text(), '{label}')]/../following-sibling::div",
                f"//td[contains(text(), '{label}')]/following-sibling::td", 
                f"//*[contains(text(), '{label}')]/parent::*/following-sibling::*"
            ]
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
            for xp in xpaths:
                try:
                    elements = driver.find_elements(By.XPATH, xp)
                    for el in elements:
                        txt = el.text.strip()
<<<<<<< HEAD
                        # Loại bỏ chính cái nhãn nếu nó bị dính vào
=======
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
                        if txt and txt != label and len(txt) > 1:
                            return txt
                except:
                    continue
        return None

<<<<<<< HEAD

    
    def scroll_and_find_click(self, driver, xpaths, step=400, max_attempts=20):
        """
        Hàm cuộn trang và thử tìm theo danh sách xpath.
        xpaths: Có thể là một chuỗi đơn hoặc một list các chuỗi xpath.
        """
        if isinstance(xpaths, str):
            xpaths = [xpaths]

        logger.info(f"-> Đang quét dọc trang để tìm một trong các phần tử...")
        
        # Đưa về đầu trang
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

        for i in range(max_attempts):
            # Tại mỗi vị trí cuộn, thử TẤT CẢ các xpath
=======
    def scroll_and_find_click(self, driver, xpaths, step=400, max_attempts=20):
        if isinstance(xpaths, str): xpaths = [xpaths]
        logger.info(f"-> Đang quét dọc trang để tìm phần tử...")
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        for i in range(max_attempts):
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
            for xp in xpaths:
                try:
                    element = driver.find_element(By.XPATH, xp)
                    if element.is_displayed():
<<<<<<< HEAD
                        # Tìm thấy! Cuộn nó vào giữa màn hình
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", element)
                        time.sleep(1)
                        
                        logger.info(f"-> Đã tìm thấy phần tử tại xpath: {xp}")
                        
                        # Thử click
=======
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", element)
                        time.sleep(1)
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
                        try:
                            element.click()
                            return True
                        except:
                            try:
                                driver.execute_script("arguments[0].click();", element)
                                return True
                            except:
                                ActionChains(driver).move_to_element(element).click().perform()
                                return True
                except:
<<<<<<< HEAD
                    pass # Không thấy xpath này, thử cái tiếp theo trong list

            # Nếu thử hết list xpath mà chưa thấy ở vị trí hiện tại -> Cuộn xuống
            driver.execute_script(f"window.scrollBy(0, {step});")
            time.sleep(0.5) 

            # Kiểm tra đáy trang
            new_height = driver.execute_script("return window.scrollY")
            total_height = driver.execute_script("return document.body.scrollHeight")
            if new_height + driver.execute_script("return window.innerHeight") >= total_height:
                logger.warning("-> Đã cuộn hết trang mà không thấy phần tử.")
                break
        
=======
                    pass
            driver.execute_script(f"window.scrollBy(0, {step});")
            time.sleep(0.5) 
            new_height = driver.execute_script("return window.scrollY")
            total_height = driver.execute_script("return document.body.scrollHeight")
            if new_height + driver.execute_script("return window.innerHeight") >= total_height:
                break
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
        return False

    # ---------------------------------------------------------
    # DATABASE ACTIONS
    # ---------------------------------------------------------
<<<<<<< HEAD

    def save_package_to_db(self, data):
        try:
            
=======
    def save_package_to_db(self, data):
        try:
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
            pkg = self.db.query(models.BiddingPackage).filter(models.BiddingPackage.ma_tbmt == data['ma_tbmt']).first()
            if not pkg:
                logger.info(f"-> [DB] INSERT NEW TBMT: {data['ma_tbmt']}")
                pkg = models.BiddingPackage(**data)
                self.db.add(pkg)
            else:
                logger.info(f"-> [DB] UPDATE TBMT: {data['ma_tbmt']}")
                for key, value in data.items():
                    if value is not None:
                        setattr(pkg, key, value)
<<<<<<< HEAD
            
=======
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
            self.db.commit()
            return pkg.hsmt_id
        except Exception as e:
            self.db.rollback()
            logger.error(f"Lỗi lưu TBMT: {e}")
            return None

    def update_file_path(self, ma_tbmt, file_path, file_name):
        try:
            pkg = self.db.query(models.BiddingPackage).filter_by(ma_tbmt=ma_tbmt).first()
            if pkg:
<<<<<<< HEAD
                new_file = models.BiddingPackageFile(hsmt_id=pkg.hsmt_id, file_name=file_name, file_type="HSMT/Webform", file_path=file_path)
=======
                new_file = models.BiddingPackageFile(
                    hsmt_id=pkg.hsmt_id, 
                    file_name=file_name, 
                    file_type="HSMT/Webform", 
                    file_path=file_path 
                )
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
                self.db.add(new_file)
                self.db.commit()
        except Exception as e:
            logger.error(f"Lỗi update file: {e}")
            
    def fill_react_datepicker(self, driver, xpath, date_str):
<<<<<<< HEAD
        """Hàm helper để điền ngày vào ô DatePicker của React/AntDesign"""
        try:
            # Tìm ô input
            element = driver.find_element(By.XPATH, xpath)
            # Xóa dữ liệu cũ (Ctrl + A -> Delete)
            element.send_keys(Keys.CONTROL + "a")
            element.send_keys(Keys.DELETE)
            time.sleep(0.5)
            # Điền ngày mới
=======
        try:
            element = driver.find_element(By.XPATH, xpath)
            element.send_keys(Keys.CONTROL + "a")
            element.send_keys(Keys.DELETE)
            time.sleep(0.5)
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
            element.send_keys(date_str)
            element.send_keys(Keys.ENTER)
            time.sleep(0.5)
        except Exception as e:
<<<<<<< HEAD
            logger.warning(f"Không điền được ngày {date_str} vào {xpath}: {e}")

    def execute_rule_search(self, rule: models.CrawlRule):
        """
        Thực hiện quy trình: Mở web -> Advanced Search -> Fill Form (theo Rule) 
        -> Chọn 50 bản ghi -> Lấy list URL -> Loop Crawl
        """
=======
            logger.warning(f"Không điền được ngày {date_str}: {e}")

    def execute_rule_search(self, rule: models.CrawlRule):
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
        logger.info(f">>> BẮT ĐẦU CHẠY RULE: {rule.rule_name}")
        driver = self.start_driver()
        if not driver: return

        try:
<<<<<<< HEAD
            # 1. Truy cập trang tìm kiếm
            url_search = "https://muasamcong.mpi.gov.vn/web/guest/contractor-selection?render=index"
            driver.get(url_search)
            
            # --- UPDATE: Chờ trang load ổn định ---
            time.sleep(5) 

            # 2. Mở "Tìm kiếm nâng cao" (QUAN TRỌNG)
            try:
                # Tìm nút có chữ "Tìm kiếm nâng cao" hoặc icon filter
                # XPath này tìm mọi phần tử có chữ 'Tìm kiếm nâng cao' để click
                btn_advanced = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Tìm kiếm nâng cao')]"))
                )
                # Chỉ click nếu chưa được mở (kiểm tra xem form đã hiện chưa)
                # Nhưng an toàn nhất là cứ click thử
                driver.execute_script("arguments[0].click();", btn_advanced)
                logger.info("-> Đã click mở Tìm kiếm nâng cao")
=======
            url_search = "https://muasamcong.mpi.gov.vn/web/guest/contractor-selection?render=index"
            driver.get(url_search)
            time.sleep(5) 

            # Advanced Search
            try:
                btn_advanced = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Tìm kiếm nâng cao')]"))
                )
                driver.execute_script("arguments[0].click();", btn_advanced)
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
                time.sleep(2)
            except:
                logger.warning("-> Không tìm thấy nút 'Tìm kiếm nâng cao' hoặc đã mở sẵn.")

<<<<<<< HEAD
            # 3. Điền thông tin (Sử dụng wait để chắc chắn ô input đã hiện)
            
            # --- A. Từ khóa ---
=======
            # Keyword
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
            if rule.keywords_include:
                keywords = rule.keywords_include
                if isinstance(keywords, list) and len(keywords) > 0:
                    kw_str = keywords[0]
                    try:
<<<<<<< HEAD
                        # --- UPDATE: XPath linh hoạt hơn (dùng contains thay vì text cứng) ---
                        inp_keyword = WebDriverWait(driver, 10).until(
                            EC.visibility_of_element_located((By.XPATH, "//input[contains(@placeholder, 'TBMT') or contains(@placeholder, 'Tên gói thầu')]"))
                        )
                        # Xóa cũ điền mới
=======
                        inp_keyword = WebDriverWait(driver, 10).until(
                            EC.visibility_of_element_located((By.XPATH, "//input[contains(@placeholder, 'TBMT') or contains(@placeholder, 'Tên gói thầu')]"))
                        )
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
                        inp_keyword.send_keys(Keys.CONTROL + "a")
                        inp_keyword.send_keys(Keys.DELETE)
                        inp_keyword.send_keys(kw_str)
                        logger.info(f"-> Đã điền từ khóa: {kw_str}")
                    except Exception as e:
                        logger.error(f"-> Không tìm thấy ô nhập từ khóa: {e}")

<<<<<<< HEAD
            # --- B. Lĩnh vực ---
            if rule.business_field:
                try:
                    # Scroll lên đầu để chắc chắn nhìn thấy checkbox
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(1)
                    
                    # Tìm label chứa text lĩnh vực (VD: "Hàng hóa") và click
                    lbl_xpath = f"//label[contains(text(), '{rule.business_field}')]"
                    chk_element = driver.find_element(By.XPATH, lbl_xpath)
                    driver.execute_script("arguments[0].click();", chk_element)
                    logger.info(f"-> Đã chọn lĩnh vực: {rule.business_field}")
                except:
                    logger.warning(f"-> Không chọn được lĩnh vực: {rule.business_field}")

            # --- C. Giá gói thầu ---
            if rule.min_budget or rule.max_budget:
                try:
                    # Tìm các ô input số tiền (thường nằm sau label Giá gói thầu)
                    inputs_price = driver.find_elements(By.XPATH, "//div[contains(text(), 'Giá gói thầu')]/..//input")
                    # Nếu không tìm thấy kiểu trên, thử tìm input có class ant-input-number
=======
            # Business Field
            if rule.business_field:
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(1)
                    lbl_xpath = f"//label[contains(text(), '{rule.business_field}')]"
                    chk_element = driver.find_element(By.XPATH, lbl_xpath)
                    driver.execute_script("arguments[0].click();", chk_element)
                except:
                    logger.warning(f"-> Không chọn được lĩnh vực: {rule.business_field}")

            # Budget
            if rule.min_budget or rule.max_budget:
                try:
                    inputs_price = driver.find_elements(By.XPATH, "//div[contains(text(), 'Giá gói thầu')]/..//input")
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
                    if not inputs_price:
                         inputs_price = driver.find_elements(By.XPATH, "//input[contains(@class, 'ant-input-number-input')]")

                    if len(inputs_price) >= 2:
<<<<<<< HEAD
                        if rule.min_budget:
                            inputs_price[0].send_keys(str(int(rule.min_budget)))
                        if rule.max_budget:
                            inputs_price[1].send_keys(str(int(rule.max_budget)))
                        logger.info("-> Đã điền khoảng giá")
                except Exception as e:
                    logger.warning(f"-> Lỗi điền giá (bỏ qua): {e}")

            # --- D. Thời gian đăng tải (Mặc định 30 ngày) ---
=======
                        if rule.min_budget: inputs_price[0].send_keys(str(int(rule.min_budget)))
                        if rule.max_budget: inputs_price[1].send_keys(str(int(rule.max_budget)))
                except Exception as e:
                    logger.warning(f"-> Lỗi điền giá: {e}")

            # Date
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
            try:
                now = datetime.now()
                from_date = (now - timedelta(days=30)).strftime("%d/%m/%Y")
                to_date = now.strftime("%d/%m/%Y")
<<<<<<< HEAD
                
                # Tìm ô ngày tháng. Thường là cặp input đầu tiên trong form
=======
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
                date_inputs = driver.find_elements(By.XPATH, "//input[contains(@placeholder, 'dd/mm/yyyy')]")
                if len(date_inputs) >= 2:
                    self.fill_react_datepicker(driver, "(//input[contains(@placeholder, 'dd/mm/yyyy')])[1]", from_date)
                    self.fill_react_datepicker(driver, "(//input[contains(@placeholder, 'dd/mm/yyyy')])[2]", to_date)
<<<<<<< HEAD
                    logger.info(f"-> Đã điền thời gian: {from_date} - {to_date}")
            except Exception as e:
                logger.warning(f"-> Lỗi điền ngày (bỏ qua): {e}")

            # 4. Nhấn nút TÌM KIẾM
            try:
                # Tìm nút button có chữ Tìm kiếm
=======
            except Exception as e:
                logger.warning(f"-> Lỗi điền ngày: {e}")

            # Search Button
            try:
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
                btn_search = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Tìm kiếm')] | //span[contains(text(), 'Tìm kiếm')]/.."))
                )
                driver.execute_script("arguments[0].click();", btn_search)
                logger.info("-> Đã nhấn nút Tìm kiếm...")
<<<<<<< HEAD
                time.sleep(5) # Chờ kết quả load
=======
                time.sleep(5)
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
            except:
                logger.error("-> Không nhấn được nút Tìm kiếm")
                return

<<<<<<< HEAD
            # 5. Chọn hiển thị 50 bản ghi
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                
                # Mở dropdown số trang (tìm cái nào đang hiện số 10 hoặc 20)
=======
            # Pagination 50
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
                dropdown = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'pagination')]//div[contains(@class, 'select')]"))
                )
                dropdown.click()
                time.sleep(1)
<<<<<<< HEAD
                
                # Chọn số 50
                opt_50 = driver.find_element(By.XPATH, "//div[contains(@title, '50') or contains(text(), '50')]")
                opt_50.click()
                logger.info("-> Đã chọn 50 bản ghi/trang")
=======
                opt_50 = driver.find_element(By.XPATH, "//div[contains(@title, '50') or contains(text(), '50')]")
                opt_50.click()
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
                time.sleep(5)
            except:
                logger.warning("-> Không chỉnh được số bản ghi (dùng mặc định).")

<<<<<<< HEAD
            # 6. Quét danh sách & Lấy Link
            list_packages = []
            try:
                # Tìm thẻ a trong cột Mã TBMT (thường màu xanh)
                # XPath: Tìm các thẻ a có href chứa 'notify-contractor'
                elements = driver.find_elements(By.XPATH, "//a[contains(@href, 'notify-contractor') and not(contains(@href, '#'))]")
                
=======
            # Get Links
            list_packages = []
            try:
                elements = driver.find_elements(By.XPATH, "//a[contains(@href, 'notify-contractor') and not(contains(@href, '#'))]")
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
                seen = set()
                for el in elements:
                    u = el.get_attribute("href")
                    if u and u not in seen:
                        seen.add(u)
                        list_packages.append(u)
<<<<<<< HEAD
                
                logger.info(f"-> Tìm thấy {len(list_packages)} gói thầu.")

=======
                logger.info(f"-> Tìm thấy {len(list_packages)} gói thầu.")
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
            except Exception as e:
                logger.error(f"-> Lỗi quét danh sách: {e}")

            driver.quit() 

<<<<<<< HEAD
            # 7. Chạy vòng lặp cào chi tiết
=======
            # Crawl Detail
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
            for idx, pkg_url in enumerate(list_packages):
                logger.info(f"=== PROCESSING {idx+1}/{len(list_packages)}: {pkg_url} ===")
                self.process_package(pkg_url)

        except Exception as e:
            logger.error(f"Lỗi fatal trong execute_rule_search: {e}")
            if driver: driver.quit()

    # ---------------------------------------------------------
    # MAIN LOGIC
    # ---------------------------------------------------------
    def process_package(self, url):
        driver = self.start_driver()
        if not driver: return

        try:
            logger.info(f"--- Đang truy cập TBMT: {url} ---")
            driver.get(url)
<<<<<<< HEAD
            
            driver.execute_script("document.body.style.zoom='70%'")
            original_url = driver.current_url
            
            # Hàm chờ thông minh (wait)
            def wait_element(xpath, timeout=20):
                return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.XPATH, xpath)))

            # Chờ trang load xong
=======
            driver.execute_script("document.body.style.zoom='70%'")
            
            def wait_element(xpath, timeout=20):
                return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.XPATH, xpath)))

>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
            wait_element("//div[contains(text(), 'Thông tin gói thầu')]")
            time.sleep(2)

            def get_txt(lbl): return self.get_info_by_label(driver, lbl)

<<<<<<< HEAD
            # --- BƯỚC 1: LẤY THÔNG TIN & LƯU DB ---
            ma_tbmt = get_txt("Mã E-TBMT") or get_txt("Mã TBMT")
            # Xử lý sạch mã KHLCNT (bỏ khoảng trắng thừa nếu có)
=======
            # BƯỚC 1: LẤY THÔNG TIN
            ma_tbmt = get_txt("Mã E-TBMT") or get_txt("Mã TBMT")
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
            raw_khlcnt = get_txt("Mã KHLCNT")
            ma_khlcnt = raw_khlcnt.strip() if raw_khlcnt else None
            
            if not ma_tbmt:
                logger.error("❌ Không lấy được Mã TBMT. Dừng.")
                return 

<<<<<<< HEAD
            # (Phần tạo dict tbmt_data GIỮ NGUYÊN code cũ của bạn, tôi rút gọn để dễ nhìn)
=======
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
            tbmt_data = {
                "ma_tbmt": ma_tbmt,
                "duong_dan_goi_thau": driver.current_url,
                "phien_ban_thay_doi": get_txt("Phiên bản thay đổi"),
                "ngay_dang_tai": self.parse_date(get_txt("Ngày đăng tải")),
                "ma_khlcnt": ma_khlcnt,
                "phan_loai_khlcnt": get_txt("Phân loại KHLCNT"),
                "ten_du_an": get_txt("Tên dự toán mua sắm") or get_txt("Tên dự án"),
                "quy_trinh_ap_dung": get_txt("Quy trình áp dụng"),
                "ten_goi_thau": get_txt("Tên gói thầu"),
                "chu_dau_tu": get_txt("Chủ đầu tư") or get_txt("Bên mời thầu"),
                "chi_tiet_nguon_von": get_txt("Chi tiết nguồn vốn"),
                "linh_vuc": get_txt("Lĩnh vực"),
                "hinh_thuc_lua_chon_nha_thau": get_txt("Hình thức LCNT") or get_txt("Hình thức lựa chọn nhà thầu"),
                "loai_hop_dong": get_txt("Loại hợp đồng"),
                "trong_nuoc_hoac_quoc_te": get_txt("Trong nước/Quốc tế") or get_txt("Trong nước/ Quốc tế"),
                "phuong_thuc_lua_chon_nha_thau": get_txt("Phương thức lựa chọn nhà thầu"),
                "thoi_gian_thuc_hien_goi_thau": get_txt("Thời gian thực hiện gói thầu"),
                "goi_thau_co_nhieu_phan_lo": get_txt("Gói thầu có nhiều phần/lô"),
                "hinh_thuc_du_thau": get_txt("Hình thức dự thầu"),
                "dia_diem_phat_hanh_e_hsmt": get_txt("Địa điểm phát hành e-HSMT") or get_txt("Địa điểm phát hành HSMT"),
                "chi_phi_nop": self.clean_money(get_txt(["Chi phí nộp e-HSDT", "Giá bán HSMT", "Chi phí nộp hồ sơ"])),
                "dia_diem_nhan_e_hsdt": get_txt("Địa điểm nhận e-HSDT") or get_txt("Địa điểm nhận HSDT"),
                "dia_diem_thuc_hien_goi_thau": get_txt("Địa điểm thực hiện gói thầu"),
                "thoi_diem_dong_thau": self.parse_date(get_txt("Thời điểm đóng thầu") or get_txt("Thời điểm kết thúc chào giá trực tuyến")),
                "thoi_diem_mo_thau": self.parse_date(get_txt("Thời điểm mở thầu") or get_txt("Thời điểm bắt đầu chào giá trực tuyến")),
                "dia_diem_mo_thau": get_txt("Địa điểm mở thầu"),
                "hieu_luc_hsdt": get_txt("Hiệu lực HSDT") or get_txt("Hiệu lực hồ sơ dự thầu"),
                "so_tien_dam_bao_du_thau": self.clean_money(get_txt("Số tiền bảo đảm dự thầu") or get_txt("Số tiền đảm bảo dự thầu")),
                "hinh_thuc_dam_bao_du_thau": get_txt("Hình thức đảm bảo dự thầu"),
                "loai_cong_trinh": get_txt("Loại công trình"),
                "so_quyet_dinh_phe_duyet": get_txt("Số quyết định phê duyệt"),
                "ngay_phe_duyet": self.parse_date(get_txt("Ngày phê duyệt")),
                "co_quan_ban_hanh_quyet_dinh": get_txt("Cơ quan ban hành quyết định"),
                "quyet_dinh_phe_duyet": get_txt("Nội dung quyết định phê duyệt") or get_txt("Quyết định phê duyệt"),
                "trang_thai": models.PackageStatus.INTERESTED
            }

            hsmt_id = self.save_package_to_db(tbmt_data)
            if not hsmt_id: return
            logger.info(f"-> Đã lưu TBMT vào DB với HSMT_ID: {hsmt_id}")

<<<<<<< HEAD
            # --- BƯỚC 3: TẢI WEBFORM (ĐÃ SỬA LỖI TAG NAME) ---
            logger.info("-> Bắt đầu bước tải HSMT...")
            driver.execute_script("window.scrollTo(0, 0)")
            
            # 1. Click Tab HSMT
            try:
                # Tìm Tab: Dùng dấu * thay vì div để tìm bất kỳ thẻ nào chứa text
=======
            # BƯỚC 3: TẢI WEBFORM & UPLOAD MINIO
            # (Đã sửa lỗi cú pháp try/except ở đây)
            try:
                logger.info("-> Bắt đầu bước tải HSMT...")
                driver.execute_script("window.scrollTo(0, 0)")
                
                # Click Tab HSMT
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
                tab_hsmt = wait_element("//*[contains(text(), 'Hồ sơ mời thầu')]", timeout=15)
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tab_hsmt)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", tab_hsmt)
<<<<<<< HEAD
                logger.info("-> Đã click Tab HSMT")
            except:
                logger.error("-> Không tìm thấy Tab HSMT!")
                return

            time.sleep(5) # Tăng thời gian chờ load bảng dữ liệu
            
            # 2. Click Nút 'Tải tất cả biểu mẫu webform'
            try:
                # --- SỬA LỖI CHÍNH Ở ĐÂY ---
                # Thay vì tìm //button, ta tìm //* (mọi thẻ)
                # Dùng normalize-space để bỏ qua các khoảng trắng thừa
                webform_xpath = "//*[contains(text(), 'Tải tất cả biểu mẫu webform')]"
                
                logger.info(f"-> Đang tìm nút Webform với xpath: {webform_xpath}")
                
                # Chờ nút xuất hiện
                btn_webform = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, webform_xpath))
                )
                
                # Scroll tới nút
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_webform)
                time.sleep(1)
                
                # Click bằng Javascript (Bắt buộc với các thẻ không phải button chuẩn)
                driver.execute_script("arguments[0].click();", btn_webform)
                logger.info("-> Đã click nút 'Tải tất cả biểu mẫu webform'")

            except Exception as e:
                # Debug: Nếu lỗi, thử in ra HTML để xem nó là thẻ gì
                logger.error(f"-> LỖI TÌM NÚT WEBFORM: {e}")
                return

            # 3. Xử lý Viewer và Tải về (Giữ nguyên)
            time.sleep(5)
            if len(driver.window_handles) > 1:
                driver.switch_to.window(driver.window_handles[-1])
                logger.info("-> Đã chuyển sang tab Viewer")
                
                try:
                    # Nút tải về trong Viewer (thường là button hoặc span)
                    btn_download = WebDriverWait(driver, 30).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Tải về')] | //span[contains(text(), 'Tải về')] | //*[text()='Tải về']"))
                    )
                    driver.execute_script("arguments[0].click();", btn_download)
                    logger.info("-> Đã nhấn Tải về. Đang đợi file...")
                    
                    # Logic chờ file (Giữ nguyên code của bạn)
                    timeout = 90
                    elapsed = 0
                    downloaded_file = None
                    while elapsed < timeout:
                        files = [f for f in os.listdir(self.download_dir) if not f.endswith('.crdownload') and not f.endswith('.tmp')]
                        if files:
                            downloaded_file = files[0]
                            break
                        time.sleep(1)
                        elapsed += 1
                    
                    if downloaded_file:
                        save_dir = os.path.join(self.base_dir, "storage", ma_tbmt.replace('/', '_'))
                        if not os.path.exists(save_dir): os.makedirs(save_dir)
                        final_path = os.path.join(save_dir, downloaded_file)
                        if os.path.exists(final_path): os.remove(final_path)
                        shutil.move(os.path.join(self.download_dir, downloaded_file), final_path)
                        logger.info(f"-> ✅ HOÀN TẤT: {final_path}")
                        self.update_file_path(ma_tbmt, final_path, downloaded_file)
                    else:
                        logger.warning("-> Timeout chờ file.")
                        
                except Exception as e:
                    logger.error(f"-> Lỗi trong tab Viewer: {e}")
            else:
                logger.warning("-> Không thấy tab Viewer bật lên.")
=======
                time.sleep(5)
                
                # Click Nút Tải
                webform_xpath = "//*[contains(text(), 'Tải tất cả biểu mẫu webform')]"
                btn_webform = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, webform_xpath)))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_webform)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", btn_webform)
                
                # Xử lý Viewer
                time.sleep(5)
                if len(driver.window_handles) > 1:
                    driver.switch_to.window(driver.window_handles[-1])
                    try:
                        btn_download = WebDriverWait(driver, 30).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Tải về')] | //span[contains(text(), 'Tải về')] | //*[text()='Tải về']"))
                        )
                        driver.execute_script("arguments[0].click();", btn_download)
                        logger.info("-> Đang đợi file tải về...")
                        
                        # Chờ File
                        timeout = 90
                        elapsed = 0
                        downloaded_file = None
                        while elapsed < timeout:
                            files = [f for f in os.listdir(self.download_dir) if not f.endswith('.crdownload') and not f.endswith('.tmp')]
                            if files:
                                downloaded_file = files[0]
                                break
                            time.sleep(1)
                            elapsed += 1
                        
                        # Upload MinIO
                        if downloaded_file:
                            full_local_path = os.path.join(self.download_dir, downloaded_file)
                            
                            # Tạo tên và đoán loại file
                            safe_ma_tbmt = ma_tbmt.replace('/', '_')
                            object_name = f"{safe_ma_tbmt}/{downloaded_file}"
                            mime_type, _ = mimetypes.guess_type(full_local_path)
                            if not mime_type: mime_type = "application/octet-stream"

                            logger.info(f"-> Đang upload MinIO: {object_name}")
                            minio_url = self.minio.upload_file(full_local_path, object_name, mime_type)
                            
                            if minio_url:
                                logger.info(f"-> Upload Xong: {minio_url}")
                                self.update_file_path(ma_tbmt, minio_url, downloaded_file)
                                try: os.remove(full_local_path)
                                except: pass
                            else:
                                logger.error("-> Upload thất bại!")
                        else:
                            logger.warning("-> Timeout: Không thấy file tải về.")
                        
                    except Exception as e:
                        logger.error(f"-> Lỗi trong tab Viewer: {e}")
                else:
                    logger.warning("-> Không thấy tab Viewer bật lên.")
                    
            except Exception as e:
                logger.error(f"-> Lỗi trong quá trình tải file: {e}")
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c

        except Exception as e:
            logger.error(f"Lỗi chung xử lý gói thầu: {e}")
        finally:
            driver.quit()
            
<<<<<<< HEAD
# =========================================================================
#  SCHEDULER: QUẢN LÝ LỊCH CHẠY
# =========================================================================
def check_and_run_schedules():
    """Hàm này sẽ được gọi mỗi phút bởi APScheduler"""
    db = SessionLocal()
    try:
        # 1. Lấy tất cả lịch đang active
        schedules = db.query(models.CrawlSchedule).filter(models.CrawlSchedule.is_active == True).all()
        
        for sched in schedules:
            # Kiểm tra xem Cron có khớp với thời điểm hiện tại (phút hiện tại) không
            # Thư viện croniter dùng để kiểm tra, hoặc dùng cơ chế của APScheduler trigger
            # Tuy nhiên, để đơn giản, ta sẽ query Rule liên quan đến Schedule này.
            
            # Ở đây mô hình dữ liệu của bạn:
            # CrawlSchedule có cron_expression.
            # Nhưng CrawlSchedule chưa thấy liên kết (Foreign Key) sang CrawlRule?
            # -> Giả sử 1 Schedule sẽ chạy TẤT CẢ các Rule, hoặc bạn cần thêm cột rule_id vào bảng Schedule.
            # -> Tạm thời: Tôi sẽ lấy TẤT CẢ Rule đang có Priority cao nhất để chạy demo.
            
            # Cách tốt hơn: Add job vào APScheduler ngay từ đầu dựa trên Cron.
            pass 

    except Exception as e:
        logger.error(f"Scheduler Error: {e}")
    finally:
        db.close()

=======
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
def run_scheduler_system():
    bot = MuasamcongDBBot()
    scheduler = BackgroundScheduler()
    db = SessionLocal()
    
<<<<<<< HEAD
    # Lấy danh sách lịch từ DB để đăng ký Job
    schedules = db.query(models.CrawlSchedule).filter(models.CrawlSchedule.is_active == True).all()
    
    logger.info(f"-> Tìm thấy {len(schedules)} lịch chạy trong DB.")
    
    for sched in schedules:
        # Tạo job cho mỗi lịch
        # Lưu ý: CronExpression trong DB cần chuẩn (VD: "0 8 * * *" - chạy 8h sáng)
        # Ta cần map Schedule ID với các Rule.
        # GIẢ ĐỊNH: Khi Schedule chạy, nó sẽ quét TOÀN BỘ bảng CrawlRule.
        
        try:
            # Hàm wrapper để chạy tất cả rule
            def job_wrapper():
                logger.info(f"⏰ ĐẾN GIỜ CHẠY SCHEDULE ID: {sched.id} ({sched.description})")
=======
    schedules = db.query(models.CrawlSchedule).filter(models.CrawlSchedule.is_active == True).all()
    logger.info(f"-> Tìm thấy {len(schedules)} lịch chạy trong DB.")
    
    for sched in schedules:
        try:
            def job_wrapper():
                logger.info(f"⏰ ĐẾN GIỜ CHẠY SCHEDULE ID: {sched.id}")
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
                with SessionLocal() as session:
                    rules = session.query(models.CrawlRule).all()
                    for rule in rules:
                        bot.execute_rule_search(rule)
            
<<<<<<< HEAD
            # Parse cron string: "minute hour day month day_of_week"
            # VD: "0 */2 * * *"
=======
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
            parts = sched.cron_expression.split()
            if len(parts) == 5:
                scheduler.add_job(
                    job_wrapper, 
<<<<<<< HEAD
                    CronTrigger(
                        minute=parts[0], hour=parts[1], day=parts[2], month=parts[3], day_of_week=parts[4]
                    ),
                    id=f"sched_{sched.id}",
                    replace_existing=True
                )
                logger.info(f"-> Đã đăng ký Job ID {sched.id} với Cron: {sched.cron_expression}")
            else:
                logger.warning(f"Cron không hợp lệ: {sched.cron_expression}")
                
=======
                    CronTrigger(minute=parts[0], hour=parts[1], day=parts[2], month=parts[3], day_of_week=parts[4]),
                    id=f"sched_{sched.id}",
                    replace_existing=True
                )
            else:
                logger.warning(f"Cron không hợp lệ: {sched.cron_expression}")
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
        except Exception as e:
            logger.error(f"Lỗi đăng ký lịch {sched.id}: {e}")
            
    db.close()
<<<<<<< HEAD
    
=======
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
    scheduler.start()
    logger.info(">>> SCHEDULER ĐANG CHẠY. NHẤN CTRL+C ĐỂ DỪNG.")
    
    try:
<<<<<<< HEAD
        while True:
            time.sleep(2)
=======
        while True: time.sleep(2)
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
            
if __name__ == "__main__":
<<<<<<< HEAD
    run_scheduler_system()
    # bot = MuasamcongDBBot()
    # # Link test
    # url = "https://muasamcong.mpi.gov.vn/web/guest/contractor-selection?p_p_id=egpportalcontractorselectionv2_WAR_egpportalcontractorselectionv2&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view&_egpportalcontractorselectionv2_WAR_egpportalcontractorselectionv2_render=detail-v2&type=es-notify-contractor&stepCode=notify-contractor-step-1-tbmt&id=f38b9a16-24ea-4665-ae4a-21b101bdd03f&notifyId=f38b9a16-24ea-4665-ae4a-21b101bdd03f&inputResultId=undefined&bidOpenId=undefined&techReqId=undefined&bidPreNotifyResultId=undefined&bidPreOpenId=undefined&processApply=LDT&bidMode=1_MTHS&notifyNo=IB2500577281&planNo=PL2500331583&pno=undefined&step=tbmt&isInternet=1&caseKHKQ=undefined&bidForm=DTRR"
    # bot.process_package(url)
=======
    run_scheduler_system()
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
