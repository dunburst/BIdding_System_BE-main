import sys
import os
import time
import logging
import io
import shutil
import re
import mimetypes 
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text 
from pytz import timezone

# Import kết nối và model
from app.infrastructure.database.database import SessionLocal, engine
from app.modules.crawler_config.model import CrawlLog, CrawlRule, CrawlSchedule # Import models của crawler_bot
from app.modules.bidding.package.model import BiddingPackage, BiddingPackageFile
from app.core.utils.enum import PackageStatus

# Import MinIO Client
from app.infrastructure.storage.minio_client import MinIOHandler

# Selenium
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger   

# Setup Logging - Đảm bảo log ra Unicode không bị lỗi
try:
    # Python 3.7+ hỗ trợ reconfigure
    # Thêm # type: ignore để Pylance không báo lỗi đỏ
    sys.stdout.reconfigure(encoding='utf-8') # type: ignore
except AttributeError:
    # Fallback cho Python cũ hơn hoặc môi trường đặc biệt
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PC1_Bot")

class MuasamcongDBBot:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.download_dir = os.path.join(self.base_dir, "downloads")
        self.driver_path = os.path.join(self.base_dir, "msedgedriver.exe")
        
        # --- Khởi tạo MinIO ---
        self.minio = MinIOHandler()

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
        
        # # Cấu hình Chrome cho Docker (Linux)
        # self.chrome_options = ChromeOptions()
        # self.chrome_options.add_argument("--window-size=1920,1080")
        # self.chrome_options.add_argument("--disable-notifications")
        # self.chrome_options.add_argument("--disable-popup-blocking")
        
        # # QUAN TRỌNG: Chạy trên Docker Linux bắt buộc phải có các dòng này
        # self.chrome_options.add_argument("--headless=new") # Chạy ẩn, không hiện giao diện
        # self.chrome_options.add_argument("--no-sandbox")
        # self.chrome_options.add_argument("--disable-dev-shm-usage")
        # self.chrome_options.add_argument("--disable-gpu")
        
        # self.prefs = {
        #     "download.default_directory": self.download_dir,
        #     "download.prompt_for_download": False,
        #     "plugins.always_open_pdf_externally": True
        # }
        # self.chrome_options.add_experimental_option("prefs", self.prefs)

    def start_driver(self):
        if not os.path.exists(self.driver_path):
            logger.error("Không tìm thấy msedgedriver.exe")
            return None
        return webdriver.Edge(service=Service(self.driver_path), options=self.edge_options)
    
        # try:
        #     # Tự động tải driver phù hợp môi trường (Windows/Linux)
        #     # Yêu cầu cài: pip install webdriver-manager
        #     return webdriver.Chrome(
        #         service=ChromeService(ChromeDriverManager().install()), 
        #         options=self.chrome_options
        #     )
        # except Exception as e:
        #     logger.error(f"Lỗi khởi động Driver: {e}")
        #     return None
    
    
    def create_crawl_log(self, rule_id):
        """Tạo log mới với trạng thái RUNNING"""
        try:
            log = CrawlLog(
                rule_id=rule_id,
                start_time=datetime.now(),
                status="RUNNING",
                packages_found=0
            )
            self.db.add(log)
            self.db.commit()
            self.db.refresh(log)
            return log.id
        except Exception as e:
            logger.error(f"Lỗi tạo log: {e}")
            return None

    def update_crawl_log(self, log_id, status, count=0, failed=0, details=None, error=None):
        """Cập nhật log khi chạy xong"""
        try:
            if not log_id: return
            
            # Nếu details là dict/list thì convert sang string json
            import json
            details_str = json.dumps(details, ensure_ascii=False) if details else None

            log = self.db.query(CrawlLog).filter_by(id=log_id).first()
            if log:
                log.end_time = datetime.now()
                log.status = status
                log.packages_found = count
                
                # --- Cập nhật trường mới ---
                log.packages_failed = failed
                log.details = details_str
                # ---------------------------
                
                log.error_message = str(error) if error else None
                self.db.commit()
        except Exception as e:
            logger.error(f"Lỗi update log: {e}")

    # ---------------------------------------------------------
    # HELPER FUNCTIONS
    # ---------------------------------------------------------
    
    # [SỬA ĐỔI] Giữ nguyên tiếng Việt, chỉ bỏ ký tự cấm của FileSystem
    def sanitize_filename(self, filename):
        # Thay thế các ký tự cấm trong tên file Windows/Linux (\ / : * ? " < > |) bằng gạch dưới
        # Nhưng vẫn GIỮ LẠI tiếng Việt có dấu
        clean_name = re.sub(r'[\\/*?:"<>|]', '_', filename)
        # Xóa khoảng trắng thừa ở đầu đuôi
        return clean_name.strip()

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
        s = str(money_str).strip().lower()
        
        # 1. Chỉ trả về 0 nếu chuỗi THỰC SỰ chỉ có chữ "không" hoặc "miễn phí"
        # Tránh bắt nhầm chữ "không" nằm giữa câu văn dài
        if s in ["không", "miễn phí", "0", "không có", "miễn phí."]:
            return 0.0
            
        # 2. Dùng Regex để chỉ lấy cụm số tiền ĐẦU TIÊN tìm thấy
        # (Thường số tiền nằm ngay đầu dòng: "117.400.000 VND...")
        # Pattern này tìm các con số liền nhau, có thể ngăn cách bởi dấu chấm
        import re
        match = re.search(r"^([\d\.]+)", s) 
        # Lưu ý: Dấu ^ ở đầu để chắc chắn lấy số ở đầu dòng, tránh lấy nhầm số nghị định phía sau
        
        if match:
            # Lấy chuỗi số tìm được (VD: "117.400.000")
            num_str = match.group(1)
            # Xóa dấu chấm phân cách hàng nghìn đi để thành số thuần (117400000)
            clean_str = num_str.replace('.', '').replace(',', '')
            try:
                return float(clean_str)
            except:
                return 0.0
                
        return 0.0
        
    def get_info_by_label(self, driver, label_patterns):
        if isinstance(label_patterns, str):
            label_patterns = [label_patterns]
        for label in label_patterns:
            xpaths = [
                f"//div[contains(text(), '{label}')]/following-sibling::div",
                f"//div[contains(@class,'row')]//div[contains(text(), '{label}')]/../following-sibling::div",
                f"//td[contains(text(), '{label}')]/following-sibling::td", 
                f"//*[contains(text(), '{label}')]/parent::*/following-sibling::*"
            ]
            for xp in xpaths:
                try:
                    elements = driver.find_elements(By.XPATH, xp)
                    for el in elements:
                        txt = el.text.strip()
                        if txt and txt != label and len(txt) > 1:
                            return txt
                except:
                    continue
        return None

    def clean_download_dir(self):
        """Xóa sạch thư mục download để tránh lấy nhầm file cũ"""
        for filename in os.listdir(self.download_dir):
            file_path = os.path.join(self.download_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                logger.warning(f"Không xóa được file cũ {file_path}: {e}")

    # ---------------------------------------------------------
    # DATABASE ACTIONS
    # ---------------------------------------------------------
    def save_package_to_db(self, data):
        try:
            pkg = self.db.query(BiddingPackage).filter(BiddingPackage.ma_tbmt == data['ma_tbmt']).first()
            if not pkg:
                logger.info(f"-> [DB] INSERT NEW TBMT: {data['ma_tbmt']}")
                pkg = BiddingPackage(**data)
                self.db.add(pkg)
            else:
                logger.info(f"-> [DB] UPDATE TBMT: {data['ma_tbmt']}")
                for key, value in data.items():
                    if value is not None:
                        setattr(pkg, key, value)
            self.db.commit()
            return pkg.hsmt_id
        except Exception as e:
            self.db.rollback()
            logger.error(f"Lỗi lưu TBMT: {e}")
            return None

    def update_file_path(self, ma_tbmt, file_path, file_name):
        try:
            pkg = self.db.query(BiddingPackage).filter_by(ma_tbmt=ma_tbmt).first()
            if pkg:
                new_file = BiddingPackageFile(
                    hsmt_id=pkg.hsmt_id, 
                    file_name=file_name, # Tên gốc (hiển thị)
                    file_type="HSMT/Webform", 
                    file_path=file_path  # URL MinIO
                )
                self.db.add(new_file)
                self.db.commit()
        except Exception as e:
            logger.error(f"Lỗi update file: {e}")
            
    def fill_react_datepicker(self, driver, xpath, date_str):
        try:
            element = driver.find_element(By.XPATH, xpath)
            element.send_keys(Keys.CONTROL + "a")
            element.send_keys(Keys.DELETE)
            time.sleep(0.5)
            element.send_keys(date_str)
            element.send_keys(Keys.ENTER)
            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"Không điền được ngày {date_str}: {e}")
            
    # ========================================================
    # [FIXED V8] NHẬP LIỆU + CLICK RA CHỖ TRỐNG AN TOÀN
    # ========================================================
    def smart_select_dropdown(self, driver, label_text, search_text):
        if not search_text: return
        
        logger.info(f"   -> [Smart Select] Xử lý '{label_text}': '{search_text}'")
        
        try:
            # 1. TÌM Ô INPUT
            xpath_strategy = f"//*[contains(text(), '{label_text}')]/ancestor::div[contains(@class, 'session') or contains(@class, 'row')]//input[contains(@class, 'ant-select-selection-search-input') or @type='text']"
            
            if len(driver.find_elements(By.XPATH, xpath_strategy)) == 0:
                 xpath_strategy = f"//*[contains(text(), '{label_text}')]/following::input[not(@type='hidden')][1]"

            input_element = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, xpath_strategy))
            )
            
            # 2. THAO TÁC NHẬP LIỆU
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", input_element)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", input_element)
            
            # Xóa sạch dữ liệu cũ
            driver.execute_script("arguments[0].value = '';", input_element)
            
            # Gõ từ khóa
            input_element.send_keys(search_text)
            time.sleep(2) # Đợi gợi ý hiện ra
            
            # 3. CHỌN GIÁ TRỊ (Nếu có dropdown)
            try:
                dropdown_chk = driver.find_elements(By.XPATH, "//div[contains(@class, 'ant-select-dropdown') and not(contains(@class, 'hidden'))]")
                if len(dropdown_chk) > 0:
                    input_element.send_keys(Keys.ENTER)
                    time.sleep(0.5)
            except:
                pass

            # 4. [SỬA LẠI] CLICK RA CHỖ TRỐNG (AN TOÀN TUYỆT ĐỐI)
            
            # Cách A: Dùng lệnh JS 'blur' để ép ô input mất focus (Giống hệt việc click ra ngoài)
            driver.execute_script("if(document.activeElement){ document.activeElement.blur(); }")
            
            # Cách B: Click vào Tiêu đề "Tìm kiếm nâng cao" (Vùng an toàn, không phải ô nhập)
            try:
                safe_zone = driver.find_element(By.XPATH, "//*[contains(text(), 'Tìm kiếm nâng cao')]")
                driver.execute_script("arguments[0].click();", safe_zone)
            except:
                # Nếu không tìm thấy tiêu đề, click vào chính cái Label của ô vừa nhập (VD: chữ "Tỉnh/ Thành phố")
                # Click vào Label không bao giờ kích hoạt input khác
                driver.find_element(By.XPATH, f"//*[contains(text(), '{label_text}')]").click()

            logger.info(f"   -> Đã Click ra vùng an toàn để trigger load dữ liệu.")
            
            # Đợi một chút để web xử lý AJAX (load xã phường...)
            time.sleep(2)

        except Exception as e:
            logger.error(f"   -> ❌ Lỗi nhập '{label_text}': {str(e).splitlines()[0]}")

    def execute_rule_search(self, rule: CrawlRule):
        logger.info(f">>> BẮT ĐẦU CHẠY RULE: {rule.rule_name}")
        log_id = self.create_crawl_log(rule.id)
        
        driver = self.start_driver()
        if not driver: 
            self.update_crawl_log(log_id, "FAILED", error="Không khởi động được Driver")
            return

        try:
            url_search = "https://muasamcong.mpi.gov.vn/web/guest/contractor-selection?render=index"
            driver.get(url_search)
            time.sleep(5) 

            # Advanced Search
            try:
                btn_advanced = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Tìm kiếm nâng cao')]"))
                )
                driver.execute_script("arguments[0].click();", btn_advanced)
                time.sleep(2)
            except:
                logger.warning("-> Không tìm thấy nút 'Tìm kiếm nâng cao' hoặc đã mở sẵn.")

            # ----------------------------------------------
            # 1. TỪ KHÓA TÌM KIẾM (Keyword Include)
            # ----------------------------------------------
            if rule.keywords_include:
                keywords = rule.keywords_include
                if isinstance(keywords, list) and len(keywords) > 0:
                    kw_str = keywords[0] # Lấy từ khóa đầu tiên (hoặc nối chuỗi nếu cần)
                    try:
                        # Tìm ô nhập từ khóa chính
                        inp_keyword = WebDriverWait(driver, 10).until(
                            EC.visibility_of_element_located((By.XPATH, "//input[contains(@placeholder, 'TBMT') or contains(@placeholder, 'Tên gói thầu')]"))
                        )
                        inp_keyword.send_keys(Keys.CONTROL + "a")
                        inp_keyword.send_keys(Keys.DELETE)
                        inp_keyword.send_keys(kw_str)
                        logger.info(f"-> Đã điền từ khóa chính: {kw_str}")
                    except Exception as e:
                        logger.error(f"-> Không tìm thấy ô nhập từ khóa: {e}")
            
            # ----------------------------------------------
            # [ĐÃ SỬA] 1b. TỪ KHÓA LOẠI TRỪ (Keyword Exclude)
            # ----------------------------------------------
            if rule.keywords_exclude:
                excludes = rule.keywords_exclude
                if isinstance(excludes, list) and len(excludes) > 0:
                    exclude_str = ", ".join(excludes) 
                    try:
                        # --- CÁCH SỬA: Dựa vào class "content__body__session__title" trong ảnh ---
                        
                        # Logic: Tìm cái tiêu đề "Không chứa từ", sau đó tìm thằng em (sibling) bên cạnh là "desc", rồi tìm input bên trong
                        xpath_exclude = "//div[contains(@class, 'content__body__session__title') and contains(text(), 'Không chứa từ')]/following-sibling::div[contains(@class, 'content__body__session__desc')]//input"
                        
                        # Backup: Nếu cách trên không được, dùng cách tìm cha (ancestor)
                        xpath_backup = "//div[contains(text(), 'Không chứa từ')]/ancestor::div[contains(@class, 'content__body__session')]//input"

                        # Thử tìm element
                        try:
                            inp_exclude = WebDriverWait(driver, 5).until(
                                EC.visibility_of_element_located((By.XPATH, xpath_exclude))
                            )
                        except:
                            # Nếu xpath chính trượt thì thử backup
                            inp_exclude = WebDriverWait(driver, 5).until(
                                EC.visibility_of_element_located((By.XPATH, xpath_backup))
                            )
                        
                        # Scroll tới đó cho chắc chắn (tránh bị menu che)
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", inp_exclude)
                        time.sleep(0.5)

                        # Xóa cũ điền mới
                        inp_exclude.send_keys(Keys.CONTROL + "a")
                        inp_exclude.send_keys(Keys.DELETE)
                        inp_exclude.send_keys(exclude_str)
                        # Bấm tab để xác nhận giá trị (phòng trường hợp web cần event blur)
                        inp_exclude.send_keys(Keys.TAB) 
                        
                        logger.info(f"-> Đã điền từ khóa loại trừ: {exclude_str}")
                    except Exception as e:
                        logger.warning(f"-> Vẫn lỗi điền 'Không chứa từ': {str(e).splitlines()[0]}")
            
            # ----------------------------------------------
            # 2. CHỦ ĐẦU TƯ (Investor)
            # ----------------------------------------------
            if rule.investor:
                for inv in rule.investor:
                    # Bây giờ chỉ cần truyền đúng chữ "Chủ đầu tư" như trên màn hình
                    self.smart_select_dropdown(driver, "Chủ đầu tư", inv)
                    time.sleep(2)

            # Business Field
            # --- C. CHỌN LĨNH VỰC (BUSINESS FIELD) ---
            if rule.business_field:
                field_text = rule.business_field.strip()
                try:
                    xpath_checkbox = f"//span[contains(text(), '{field_text}')] | //label[contains(., '{field_text}')]"
                    chk_element = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xpath_checkbox)))
                    
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", chk_element)
                    time.sleep(1) 
                    driver.execute_script("arguments[0].click();", chk_element)
                    
                    logger.info(f"-> [3/7] Đã tick lĩnh vực: {field_text}")
                    time.sleep(3) # BẮT BUỘC: Đợi web reload lại sau khi tick checkbox
                except Exception as e:
                    logger.warning(f"-> Lỗi chọn lĩnh vực: {e}")
                    
            # --- D. CHỌN TỈNH / THÀNH PHỐ (QUAN TRỌNG) ---
            has_location = False
            if rule.locations and len(rule.locations) > 0:
                has_location = True
                for loc in rule.locations:
                    self.smart_select_dropdown(driver, "Tỉnh/ Thành phố", loc)
                    
                    # [QUAN TRỌNG] Sau khi click ra ngoài ở hàm trên, web sẽ xoay loading ô Xã/Phường
                    # Ta cần đợi ô Xã/Phường SẴN SÀNG (Enabled) trước khi điền
                    logger.info("   -> Đang đợi ô Xã/Phường kích hoạt...")
                    time.sleep(2) 

            # --- E. CHỌN XÃ / PHƯỜNG ---
            if rule.commune and len(rule.commune) > 0:
                if has_location:
                    for com in rule.commune:
                        self.smart_select_dropdown(driver, "Xã/ Phường", com)
                else:
                    logger.warning("-> Bỏ qua Xã/Phường vì chưa chọn Tỉnh.")

            # Budget
            if rule.min_budget or rule.max_budget:
                try:
                    inputs_price = driver.find_elements(By.XPATH, "//div[contains(text(), 'Giá gói thầu')]/..//input")
                    if not inputs_price:
                         inputs_price = driver.find_elements(By.XPATH, "//input[contains(@class, 'ant-input-number-input')]")

                    if len(inputs_price) >= 2:
                        if rule.min_budget: inputs_price[0].send_keys(str(int(rule.min_budget)))
                        if rule.max_budget: inputs_price[1].send_keys(str(int(rule.max_budget)))
                except Exception as e:
                    logger.warning(f"-> Lỗi điền giá: {e}")

            # Date
            try:
                now = datetime.now()
                from_date = (now - timedelta(days=1)).strftime("%d/%m/%Y")
                to_date = now.strftime("%d/%m/%Y")
                date_inputs = driver.find_elements(By.XPATH, "//input[contains(@placeholder, 'dd/mm/yyyy')]")
                if len(date_inputs) >= 2:
                    self.fill_react_datepicker(driver, "(//input[contains(@placeholder, 'dd/mm/yyyy')])[1]", from_date)
                    self.fill_react_datepicker(driver, "(//input[contains(@placeholder, 'dd/mm/yyyy')])[2]", to_date)
            except Exception as e:
                logger.warning(f"-> Lỗi điền ngày: {e}")
                
            # ==================================================================
            # GIAI ĐOẠN 2: BẤM TÌM KIẾM
            # ==================================================================
            logger.info(">>> ĐÃ NHẬP XONG. CLICK NÚT TÌM KIẾM <<<")
            
            # Đảm bảo click ra ngoài lần cuối để đóng mọi dropdown che khuất nút tìm kiếm
            driver.find_element(By.TAG_NAME, "body").click()
            time.sleep(1)

            try:
                btn_search = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Tìm kiếm')] | //span[contains(text(), 'Tìm kiếm')]/.."))
                )
                driver.execute_script("arguments[0].click();", btn_search)
                logger.info("-> ĐÃ CLICK NÚT TÌM KIẾM!")
                time.sleep(5)
            except Exception as e:
                logger.error(f"-> Lỗi bấm nút Tìm kiếm: {e}")

            # ---------------------------------------------------------
            # [BỔ SUNG] CHỌN HIỂN THỊ 50 BẢN GHI/TRANG
            # ---------------------------------------------------------
            try:
                # 1. Scroll xuống cuối trang
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)

                # 2. Tìm thẻ <select> chứa option 50
                # XPath này nghĩa là: Tìm thẻ select nào mà bên trong nó có option giá trị là '50'
                # Đây là cách tìm chính xác nhất dựa trên ảnh bạn gửi
                select_xpath = "//select[./option[@value='50']]"
                
                select_element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, select_xpath))
                )
                
                # 3. Sử dụng thư viện Select của Selenium để chọn
                select_obj = Select(select_element)
                select_obj.select_by_value("50")
                
                logger.info("-> Đã chọn hiển thị 50 bản ghi/trang.")

                # 4. Đợi trang load lại dữ liệu
                time.sleep(5)

            except Exception as e:
                logger.warning(f"-> Không thay đổi được số bản ghi: {str(e)}")
            
            # ---------------------------------------------------------

            # Get Links
            list_packages = []
            try:
                elements = driver.find_elements(By.XPATH, "//a[contains(@href, 'notify-contractor') and not(contains(@href, '#'))]")
                seen = set()
                for el in elements:
                    u = el.get_attribute("href")
                    if u and u not in seen:
                        seen.add(u)
                        list_packages.append(u)
                logger.info(f"-> Tìm thấy {len(list_packages)} gói thầu.")
            except Exception as e:
                logger.error(f"-> Lỗi quét danh sách: {e}")

            driver.quit() 

            # Crawl Detail
            success_count = 0
            fail_count = 0
            fail_details = [] # Danh sách lưu chi tiết lỗi

            for idx, pkg_url in enumerate(list_packages):
                logger.info(f"=== PROCESSING {idx+1}/{len(list_packages)}: {pkg_url} ===")
                try:
                    # Gọi hàm xử lý (Hàm này nên raise Exception nếu lỗi)
                    self.process_package(pkg_url)
                    success_count += 1
                except Exception as e:
                    fail_count += 1
                    error_msg = str(e)
                    logger.error(f"Lỗi gói {pkg_url}: {error_msg}")
                    
                    # Lưu lại link và lý do lỗi vào list để update vào DB
                    fail_details.append({
                        "url": pkg_url,
                        "error": error_msg
                    })
            
            # Xác định trạng thái cuối cùng của cả Rule
            final_status = "SUCCESS"
            if fail_count > 0:
                # Nếu có cái thành công, có cái thất bại -> WARNING
                # Nếu chết sạch -> FAILED
                final_status = "WARNING" if success_count > 0 else "FAILED"
            
            # Update Log với đầy đủ thông tin thống kê
            self.update_crawl_log(
                log_id, 
                status=final_status, 
                count=success_count, 
                failed=fail_count,    # Số lượng lỗi
                details=fail_details  # Chi tiết lỗi (JSON)
            )
            # ========================================================

        except Exception as e:
            logger.error(f"Lỗi fatal trong execute_rule_search: {e}")
            self.update_crawl_log(log_id, "CRASHED", error=str(e))
            if driver: 
                try: driver.quit()
                except: pass

    # ---------------------------------------------------------
    # MAIN LOGIC
    # ---------------------------------------------------------
    def process_package(self, url):
        driver = self.start_driver()
        if not driver: return

        try:
            logger.info(f"--- Đang truy cập TBMT: {url} ---")
            driver.get(url)
            driver.execute_script("document.body.style.zoom='70%'")
            
            def wait_element(xpath, timeout=20):
                return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.XPATH, xpath)))

            wait_element("//div[contains(text(), 'Thông tin gói thầu')]")
            time.sleep(2)

            def get_txt(lbl): return self.get_info_by_label(driver, lbl)

            # BƯỚC 1: LẤY THÔNG TIN
            ma_tbmt = get_txt("Mã E-TBMT") or get_txt("Mã TBMT")
            # Lấy phiên bản đang hiển thị (Mặc định web load là bản mới nhất)
            phien_ban_str = get_txt("Phiên bản thay đổi")
            def extract_ver_num(ver_str):
                if not ver_str: return -1
                # 1. Tìm TẤT CẢ các cụm số trong chuỗi (VD: "00 01" -> ['00', '01'])
                numbers = re.findall(r'\d+', str(ver_str))
                
                if numbers:
                    # 2. Chuyển sang int và lấy số LỚN NHẤT (max)
                    # VD: [0, 1] -> lấy 1
                    return max(map(int, numbers))
                    
                return -1
            ver_num = extract_ver_num(phien_ban_str)
            if ver_num >= 0:
                clean_ver = f"{ver_num:02d}" 
            else: 
                clean_ver = "00"
            raw_khlcnt = get_txt("Mã KHLCNT")
            ma_khlcnt = raw_khlcnt.strip() if raw_khlcnt else None
            
            if not ma_tbmt:
                logger.error("❌ Không lấy được Mã TBMT. Dừng.")
                return 

            tbmt_data = {
                "ma_tbmt": ma_tbmt,
                "duong_dan_goi_thau": driver.current_url,
                "phien_ban_thay_doi": clean_ver,
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
                "trang_thai": PackageStatus.INTERESTED
            }

            hsmt_id = self.save_package_to_db(tbmt_data)
            if not hsmt_id: 
                raise Exception("Lỗi lưu Database (hsmt_id is None)")
            logger.info(f"-> Đã lưu TBMT vào DB với HSMT_ID: {hsmt_id}")

            # BƯỚC 3: TẢI WEBFORM & UPLOAD MINIO
            try:
                # [QUAN TRỌNG] Dọn dẹp thư mục download trước khi tải
                self.clean_download_dir()

                logger.info("-> Bắt đầu bước tải HSMT...")
                driver.execute_script("window.scrollTo(0, 0)")
                
                # 1. Click Tab "Hồ sơ mời thầu"
                tab_hsmt = wait_element("//*[contains(text(), 'Hồ sơ mời thầu')]", timeout=15)
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tab_hsmt)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", tab_hsmt)
                time.sleep(3)
                
                # 2. Click Nút "Tải tất cả biểu mẫu webform"
                webform_xpath = "//*[contains(text(), 'Tải tất cả biểu mẫu webform')]"
                btn_webform = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, webform_xpath)))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_webform)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", btn_webform)
                
                # 3. Xử lý Viewer (Tab mới)
                time.sleep(10)
                if len(driver.window_handles) > 1:
                    driver.switch_to.window(driver.window_handles[-1])
                    logger.info("-> Đã chuyển sang tab Viewer.")
                    
                    clicked = False
                    try:
                        # --- [CHIẾN THUẬT 1] TÌM NGAY Ở KHUNG CHÍNH (MAIN FRAME) ---

                        btn_xpath = "//button[contains(@class, 'btn-primary') and contains(., 'Tải về')]"
                        
                        logger.info("-> Đang tìm nút Tải về (btn-primary) ở Main Frame...")
                        btn = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, btn_xpath))
                        )
                        
                        # Dùng Javascript click để chắc chắn ăn
                        driver.execute_script("arguments[0].click();", btn)
                        logger.info("-> Đã Click nút Tải về thành công!")
                        clicked = True
                        
                    except Exception as e:
                        logger.warning(f"-> Không thấy ở Main Frame ({e}). Đang thử tìm trong các Iframe...")
                        
                        # --- [CHIẾN THUẬT 2] CHỈ TÌM TRONG IFRAME NẾU BƯỚC 1 THẤT BẠI ---
                        iframes = driver.find_elements(By.TAG_NAME, "iframe")
                        for i, frame in enumerate(iframes):
                            try:
                                driver.switch_to.frame(frame)
                                # Tìm lại với xpath rộng hơn một chút
                                btn = WebDriverWait(driver, 2).until(
                                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Tải về')] | //a[contains(., 'Tải về')]"))
                                )
                                driver.execute_script("arguments[0].click();", btn)
                                logger.info(f"-> Đã Click được trong Iframe số {i}")
                                clicked = True
                                break # Thoát vòng lặp iframe nếu đã click được
                            except:
                                # Quay ra để thử iframe khác hoặc thử phương án khác
                                driver.switch_to.default_content() 
                                if len(driver.window_handles) > 1: driver.switch_to.window(driver.window_handles[-1])

                    # --- [CHIẾN THUẬT 3] ĐƯỜNG CÙNG - DÙNG PHÍM TẮT CTRL+S ---
                    if not clicked:
                        logger.error("-> Vẫn không click được. Dùng phím tắt Ctrl+S...")
                        try:
                            # Đảm bảo đang ở main frame để gửi phím
                            driver.switch_to.default_content() 
                            if len(driver.window_handles) > 1: driver.switch_to.window(driver.window_handles[-1])
                            
                            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.CONTROL, 's')
                        except Exception as k_err:
                            logger.error(f"-> Gửi phím tắt thất bại: {k_err}")

                    # 4. CHỜ FILE TẢI VỀ (Code cũ giữ nguyên)
                    logger.info("-> Đang đợi file xuất hiện trong thư mục...")
                    timeout = 90 
                    elapsed = 0
                    downloaded_file = None
                    
                    while elapsed < timeout:
                        files = [f for f in os.listdir(self.download_dir) if not f.endswith('.crdownload') and not f.endswith('.tmp')]
                        if files:
                            # Sắp xếp lấy file mới nhất
                            files.sort(key=lambda x: os.path.getmtime(os.path.join(self.download_dir, x)), reverse=True)
                            
                            # Check size > 0
                            potential_file = files[0]
                            if os.path.getsize(os.path.join(self.download_dir, potential_file)) > 0:
                                downloaded_file = potential_file
                                break
                        time.sleep(1)
                        elapsed += 1
                        
                    # 5. Upload MinIO
                    if downloaded_file:
                        full_local_path = os.path.join(self.download_dir, downloaded_file)
                        
                        # [FIX] Dùng hàm sanitize vừa thêm
                        safe_filename = self.sanitize_filename(downloaded_file)
                        
                        # Xử lý folder path (thay / bằng _ trong mã TBMT)
                        safe_ma_tbmt = ma_tbmt.replace('/', '_').replace(' ', '').strip()
                        
                        # Tạo Object Name: Giữ nguyên tiếng Việt
                        object_name = f"{safe_ma_tbmt}/{safe_filename}"
                        
                        mime_type, _ = mimetypes.guess_type(full_local_path)
                        if not mime_type: mime_type = "application/octet-stream"

                        logger.info(f"-> Đang upload MinIO: {object_name}")
                        minio_url = self.minio.upload_file(full_local_path, object_name, mime_type)
                        
                        if minio_url:
                            logger.info(f"-> Upload Xong: {minio_url}")
                            # Cập nhật DB
                            self.update_file_path(ma_tbmt, minio_url, downloaded_file)
                            # Xóa file local sau khi up xong
                            try: os.remove(full_local_path)
                            except: pass
                        else:
                            logger.error("-> Upload thất bại (MinIO trả về None).")
                    else:
                        logger.warning("-> Timeout: Không thấy file tải về sau 60s.")
                        # Chụp ảnh lỗi nếu không thấy file
                        driver.save_screenshot(os.path.join(self.base_dir, f"error_no_file_{ma_tbmt.replace('/','_')}.png"))
                
                else:
                    logger.warning("-> Không thấy tab Viewer bật lên (Popup blocked?).")
                    
            except Exception as e:
                logger.error(f"-> Lỗi trong quá trình tải file: {e}")

        except Exception as e:
            logger.error(f"Chi tiết lỗi process_package: {e}")
            raise e
        finally:
            driver.quit()
            
# Biến toàn cục để lưu scheduler
global_scheduler = None

def load_jobs_from_db(scheduler):
    """Hàm này xóa hết job cũ và nạp lại job mới từ Database"""
    try:
        # 1. Xóa sạch các job cũ đang chạy để tránh trùng lặp
        scheduler.remove_all_jobs()
        logger.info("-> [Reload] Đã xóa các lịch trình cũ.")

        # 2. Kết nối DB lấy lịch mới
        with SessionLocal() as db:
            schedules = db.query(CrawlSchedule).filter(CrawlSchedule.is_active == True).all()
            logger.info(f"-> [Reload] Tìm thấy {len(schedules)} lịch active trong DB.")
            
            for sched in schedules:
                # --- JOB WRAPPER (Giữ nguyên logic cũ) ---
                def job_wrapper(s_id=sched.id): 
                    logger.info(f"⏰ [Auto] ĐẾN GIỜ CHẠY SCHEDULE ID: {s_id}")
                    try:
                        bot = MuasamcongDBBot() 
                        with SessionLocal() as session:
                            # --- [CẬP NHẬT QUAN TRỌNG] ---
                            # Chỉ lấy các Rule có trạng thái is_active = True
                            rules = session.query(CrawlRule).filter(CrawlRule.is_active == True).all()
                            
                            logger.info(f"-> Tìm thấy {len(rules)} luật (Rules) đang kích hoạt.")
                            for rule in rules:
                                bot.execute_rule_search(rule)
                    except Exception as e:
                        logger.error(f"❌ Lỗi Job {s_id}: {e}")

                # --- ADD JOB ---
                parts = sched.cron_expression.split()
                if len(parts) == 5:
                    trigger = CronTrigger(
                        minute=parts[0], hour=parts[1], day=parts[2], month=parts[3], day_of_week=parts[4],
                        timezone="Asia/Ho_Chi_Minh"
                    )
                    scheduler.add_job(
                        job_wrapper, 
                        trigger, 
                        id=f"sched_{sched.id}", 
                        replace_existing=True
                    )
                    logger.info(f"   + Đã nạp lịch ID {sched.id}: {sched.cron_expression}")

        # In ra lịch trình mới để kiểm tra
        print("\n--- LỊCH TRÌNH ĐÃ CẬP NHẬT ---")
        scheduler.print_jobs()
        print("------------------------------\n")

    except Exception as e:
        logger.error(f"Lỗi khi nạp lại Job: {e}")

def start_scheduler_service():
    """Hàm khởi động ban đầu"""
    global global_scheduler
    
    # Khởi tạo Scheduler nếu chưa có
    if global_scheduler is None:
        global_scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
        global_scheduler.start()
        logger.info(">>> SCHEDULER STARTED <<<")
    
    # Gọi hàm nạp job lần đầu
    load_jobs_from_db(global_scheduler)
    
    return global_scheduler

def reload_scheduler():
    """Hàm này được gọi từ API để làm mới lịch"""
    global global_scheduler
    if global_scheduler and global_scheduler.running:
        load_jobs_from_db(global_scheduler)
        return True
    return False

def run_scheduler_system():
    scheduler = start_scheduler_service()
    if scheduler:
        try:
            while True: time.sleep(2)
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()
            
if __name__ == "__main__":
    # --- TEST RIÊNG CHO 1 LINK CỤ THỂ ---
    # print("!!! ĐANG CHẠY CHẾ ĐỘ THỦ CÔNG (TEST LINK LẺ) !!!") 
    
    # # Link gói thầu bạn muốn test
    # target_url = "https://muasamcong.mpi.gov.vn/web/guest/contractor-selection?p_p_id=egpportalcontractorselectionv2_WAR_egpportalcontractorselectionv2&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view&_egpportalcontractorselectionv2_WAR_egpportalcontractorselectionv2_render=detail-v2&type=es-notify-contractor&stepCode=notify-contractor-step-4-kqlcnt&id=9ede5000-9134-4f82-906f-79ae559d7aee&notifyId=9ede5000-9134-4f82-906f-79ae559d7aee&inputResultId=c5be4e20-9e84-4f67-bd18-e16dc372c715&bidOpenId=4940bce6-9c3c-4536-b2f6-0d1020e2b8bf&techReqId=undefined&bidPreNotifyResultId=undefined&bidPreOpenId=undefined&processApply=LDT&bidMode=1_MTHS&notifyNo=IB2500166683&planNo=PL2500074522&pno=undefined&step=tbmt&isInternet=1&caseKHKQ=undefined&bidForm=DTRR"

    # print(f"🚀 BẮT ĐẦU CHẠY NGAY LẬP TỨC CHO LINK:\n{target_url}")
    
    # try:
    #     # Khởi tạo Bot
    #     bot = MuasamcongDBBot()
        
    #     # Chạy hàm xử lý
    #     bot.process_package(target_url)
        
    #     print("✅ ĐÃ CHẠY XONG!")
    # except Exception as e:
    #     print(f"❌ CÓ LỖI XẢY RA: {e}")
    #     # In thêm chi tiết lỗi để debug nếu cần
    #     import traceback
    #     traceback.print_exc()
    
    # TEST TÌM KIẾM NÂNG CAO VƠI RULE TRONG DB
    # print("!!! ĐANG CHẠY CHẾ ĐỘ TEST THỦ CÔNG (DEBUG) !!!")
    # db = SessionLocal()
    
    # try:
    #     # Lấy Rule mới nhất vừa thêm vào DB (Sắp xếp ID giảm dần lấy cái đầu tiên)
    #     # Hoặc bạn có thể filter theo ID cụ thể: .filter(models.CrawlRule.id == 10)
    #     rule = db.query(models.CrawlRule)\
    #         .filter(models.CrawlRule.is_active == True) \
    #         .order_by(models.CrawlRule.id.desc())\
    #         .first()
        
    #     if not rule:
    #         print("❌ Không tìm thấy Rule nào trong Database. Hãy chạy câu lệnh SQL insert trước!")
    #     else:
    #         print(f"🚀 Đang test Rule ID: {rule.id}")
    #         print(f"   - Tên: {rule.rule_name}")
    #         print(f"   - Tỉnh: {rule.locations}")
    #         print(f"   - Chủ đầu tư: {rule.investor}")
    #         print(f"   - Xã/Phường: {rule.commune}")
            
    #         # 2. Khởi tạo Bot và chạy
    #         bot = MuasamcongDBBot()
    #         bot.execute_rule_search(rule)
            
    #         print("✅ ĐÃ CHẠY XONG QUY TRÌNH TEST!")

    # except Exception as e:
    #     print(f"❌ LỖI TEST: {e}")
    # finally:
    #     db.close()
        
    # # KHỞI ĐỘNG HỆ THỐNG SCHEDULER(MAIN)
    run_scheduler_system()