import sys
import os
import time
import logging
import re
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session
from app.infrastructure.database.database import SessionLocal
from app.modules.bidding.package.model import BiddingPackage, BiddingPackageFile
from app.core.utils.enum import PackageStatus
from app.modules.bidding.result.model import BiddingResult, BiddingResultWinner, BiddingResultFailed, BiddingResultItem 

# Selenium Imports
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - ResultBot - %(message)s')
logger = logging.getLogger("ResultBot")

class ResultCrawlerBot:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.driver_path = os.path.join(self.base_dir, "msedgedriver.exe")
        self.db: Session = SessionLocal()
        
        self.edge_options = Options()
        self.edge_options.add_argument("--window-size=1920,1080")
        self.edge_options.add_argument("--disable-notifications")
        self.edge_options.add_argument("--disable-popup-blocking")

    def start_driver(self):
        if not os.path.exists(self.driver_path):
            logger.error("Driver not found at: " + self.driver_path)
            return None
        return webdriver.Edge(service=Service(self.driver_path), options=self.edge_options)

    # --- 1. CLEAN MONEY (Improved) ---
    def clean_money(self, money_str):
        if not money_str: return 0
        # If it contains date characters, it's not money
        if "/" in str(money_str) or ":" in str(money_str): return 0
        
        # Remove non-digits
        clean_str = re.sub(r'[^\d]', '', str(money_str))
        try:
            val = float(clean_str)
            # Sanity check: if > 1 quadrillion, it's likely an error
            if val > 1_000_000_000_000_000: return 0
            return val
        except:
            return 0
    
    def parse_date(self, date_str):
        if not date_str: return None
        # Clean newline chars often found in this UI
        date_str = date_str.replace('\n', ' ').strip()
        # Find first date pattern dd/mm/yyyy
        match = re.search(r'\d{2}/\d{2}/\d{4}', date_str)
        if match:
            try: return datetime.strptime(match.group(0), "%d/%m/%Y")
            except: pass
        return None

    # --- 2. GET TEXT BY LABEL (FIXED: "Everything is date" error) ---
    # --- [FIX QUAN TRỌNG] TÌM TEXT TRONG FLEXBOX ---
    def get_info_by_label(self, driver, label_list):
        if isinstance(label_list, str): label_list = [label_list]
        for label in label_list:
            # Chiến thuật: Tìm text label -> Nhảy ra div cha (row) -> Lấy div cuối cùng (value)
            # Áp dụng cho cấu trúc: <div class="d-flex"><div class="title">Label</div><div>Value</div></div>
            xpaths = [
                # Cách 1: Chuẩn cho muasamcong mới (dựa trên ảnh image_6273ec.png)
                f"//span[contains(text(), '{label}')]/ancestor::div[contains(@class, 'd-flex')]/div[last()]",
                f"//div[contains(text(), '{label}')]/ancestor::div[contains(@class, 'd-flex')]/div[last()]",
                f"//*[contains(text(), '{label}')]/ancestor::div[contains(@class, 'd-flex')]/div[last()]",
                
                # Cách 2: Grid column
                f"//*[contains(text(), '{label}')]/ancestor::div[contains(@class, 'col')]/following-sibling::div",
                
                # Cách 3: Sibling cổ điển
                f"//*[contains(text(), '{label}')]/following-sibling::div",
                f"//td[contains(text(), '{label}')]/following-sibling::td"
            ]
            
            for xp in xpaths:
                try:
                    elems = driver.find_elements(By.XPATH, xp)
                    for el in elems:
                        txt = el.text.strip()
                        # Kiểm tra: Text lấy được không được trùng với label (tránh lấy chính nó)
                        if txt and label not in txt and len(txt) < 500: 
                            return txt
                except: continue
        return None

    def get_link_by_label(self, driver, label):
        try:
            # Enhanced link finding: Look for 'a' tags in the same structural block
            # Specifically targets links that likely point to files (.pdf etc or just normal links)
            xpath = f"//*[contains(text(), '{label}')]/ancestor::div[contains(@class, 'd-flex') or contains(@class, 'row')]//a"
            elems = driver.find_elements(By.XPATH, xpath)
            for el in elems:
                href = el.get_attribute('href')
                if href and "javascript" not in href:
                    return href
        except: pass
        return None
    
    # --- [NEW] LOGIC XỬ LÝ MÃ SỐ THUẾ ---
    def clean_tax_code_logic(self, tax_code, bidder_code):
        # 1. Nếu có mã số thuế và không rỗng -> Dùng luôn
        if tax_code and str(tax_code).strip():
            return str(tax_code).strip()
        
        # 2. Nếu không có mã số thuế -> Fallback sang Mã định danh
        if bidder_code and str(bidder_code).strip():
            # Dùng Regex xóa bỏ mọi ký tự KHÔNG PHẢI SỐ (chữ cái, khoảng trắng...)
            # VD: "vn12345" -> "12345", "VN-999" -> "999"
            clean_code = re.sub(r'\D', '', str(bidder_code))
            return clean_code
            
        return None
    
    # ==============================================================================
    # [TRỌNG TÂM] HÀM XỬ LÝ BẢNG HTML CÓ GỘP Ô (ROWSPAN)
    # Hàm này sẽ "phẳng hóa" bảng: Nếu ô được gộp, nó sẽ copy giá trị xuống các dòng dưới
    # ==============================================================================
    def parse_html_table_with_rowspan(self, table_element):
        # 1. Lấy tên các cột (Headers)
        headers = []
        # Chỉ lấy dòng header cuối cùng nếu có nhiều dòng header (đơn giản hóa)
        header_rows = table_element.find_elements(By.XPATH, ".//thead/tr")
        if header_rows:
            header_cells = header_rows[-1].find_elements(By.TAG_NAME, "th")
            if not header_cells: header_cells = header_rows[-1].find_elements(By.TAG_NAME, "td")
        else:
            # Fallback nếu không có thead
            header_cells = table_element.find_elements(By.XPATH, ".//tr[1]/td | .//tr[1]/th")
            
        for cell in header_cells:
            headers.append(cell.text.lower().replace('\n', ' ').strip())

        # 2. Đọc dữ liệu Body và xử lý Grid
        body_rows = table_element.find_elements(By.XPATH, ".//tbody/tr")
        num_rows = len(body_rows)
        num_cols = len(headers)
        
        # Tạo ma trận trống để chứa dữ liệu (Matrix)
        # grid[row][col] = text
        grid = [['' for _ in range(num_cols)] for _ in range(num_rows)]
        
        # Ma trận đánh dấu ô đã được điền (do rowspan từ dòng trên)
        occupied = [[False for _ in range(num_cols)] for _ in range(num_rows)]

        for r_idx, row in enumerate(body_rows):
            cells = row.find_elements(By.TAG_NAME, "td")
            c_ptr = 0 # Con trỏ cột thực tế trong HTML
            
            for c_idx in range(num_cols):
                # Nếu ô này đã bị chiếm bởi rowspan của dòng trước -> Bỏ qua, lấy giá trị đã điền sẵn
                if occupied[r_idx][c_idx]:
                    continue
                
                # Nếu hết cell trong HTML thì dừng (dù grid còn chỗ)
                if c_ptr >= len(cells): 
                    break

                cell = cells[c_ptr]
                text_val = cell.text.strip()
                
                # Lấy thuộc tính rowspan (mặc định là 1)
                rowspan = int(cell.get_attribute("rowspan")) if cell.get_attribute("rowspan") else 1
                
                # Điền giá trị vào ô hiện tại VÀ các ô phía dưới (theo rowspan)
                for i in range(rowspan):
                    target_row = r_idx + i
                    if target_row < num_rows:
                        grid[target_row][c_idx] = text_val # Copy giá trị xuống
                        occupied[target_row][c_idx] = True # Đánh dấu là đã có dữ liệu
                
                c_ptr += 1 # Chuyển sang cell HTML tiếp theo

        # 3. Chuyển Grid thành List of Dict để dễ map
        result_data = []
        for r in range(num_rows):
            row_dict = {}
            has_data = False
            for c in range(num_cols):
                row_dict[headers[c]] = grid[r][c]
                if grid[r][c]: has_data = True
            
            # Chỉ lấy dòng có dữ liệu
            if has_data:
                result_data.append(row_dict)
                
        return result_data

    # Helper tìm giá trị trong dict dựa trên từ khóa (vì tên cột có thể thay đổi chút ít)
    def get_val(self, row_dict, keywords):
        for header, val in row_dict.items():
            for kw in keywords:
                if kw in header:
                    return val
        return None

    # --- 3. SCRAPE GENERAL INFO ---
    def scrape_general_info(self, driver):
        info = {}
        try:
            # Wait for content to load
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CLASS_NAME, "card")))

            info["result_status"] = self.get_info_by_label(driver, ["Trạng thái KQLCNT"])
            info["posting_date"] = self.parse_date(self.get_info_by_label(driver, ["Ngày đăng tải"]))
            
            # Added "sau khi" to be specific for the budget field
            info["approved_budget"] = self.clean_money(self.get_info_by_label(driver, ["Dự toán gói thầu được duyệt"]))
            info["package_price"] = self.clean_money(self.get_info_by_label(driver, ["Giá gói thầu"]))
            
            info["approval_date"] = self.parse_date(self.get_info_by_label(driver, ["Ngày phê duyệt"]))
            info["approving_agency"] = self.get_info_by_label(driver, ["Cơ quan phê duyệt"])
            
            raw_decision = self.get_info_by_label(driver, ["Số quyết định phê duyệt"])
            info["decision_number"] = raw_decision[:100] if raw_decision else None
            
            info["decision_link"] = self.get_link_by_label(driver, "Quyết định phê duyệt")
            info["ehsdt_report_link"] = self.get_link_by_label(driver, "Báo cáo đánh giá tổng hợp E-HSDT")
            
            # This field usually has the same structure
            info["bidding_result_text"] = self.get_info_by_label(driver, ["Kết quả đấu thầu"])

        except Exception as e:
            logger.warning(f"Error scraping General Info: {e}")
        return info

    # --- HELPER: MAP COLUMNS ---
    def get_column_indices(self, header_elements, mapping_config):
        indices = {}
        # Normalize: lowercase, remove newlines to handle "Giá dự thầu\n(VND)"
        headers_text = [h.text.lower().replace('\n', ' ').strip() for h in header_elements]
        
        for key, possible_names in mapping_config.items():
            for idx, text in enumerate(headers_text):
                if any(p_name in text for p_name in possible_names):
                    indices[key] = idx
                    break
        return indices
    
    def get_cell_text(self, cells, index):
        if index is not None and index < len(cells):
            return cells[index].text.strip()
        return None

    # --- 2. CÀO WINNERS (LOGIC FILL-DOWN MẠNH MẼ) ---
    def scrape_winners(self, driver):
        winners_list = []
        try:
            xpath = "//div[contains(text(), 'Thông tin Nhà thầu trúng thầu')]/ancestor::div[contains(@class,'card')]//table"
            try: table = driver.find_element(By.XPATH, xpath)
            except: return []
            
            flat_rows = self.parse_html_table_with_rowspan(table)
            
            # --- BỘ NHỚ TẠM (CACHE) CHO DỮ LIỆU CHUNG ---
            # Dùng để lưu trữ thông tin của dòng "cha" (Leader liên danh)
            shared_data = {
                "jv_name": None, "bid_price": 0, "win_price": 0, "eval_price": 0, "correct_price": 0,
                "tech_score": None, "exec_time": None, "contract_time": None, "other": None
            }

            for row in flat_rows:
                b_name = self.get_val(row, ["tên nhà thầu"])
                if not b_name: continue
                
                # --- [UPDATE] XỬ LÝ MÃ SỐ THUẾ TẠI ĐÂY ---
                raw_bidder_code = self.get_val(row, ["mã định danh"])
                raw_tax_code = self.get_val(row, ["mã số thuế"])
                
                final_tax_code = self.clean_tax_code_logic(raw_tax_code, raw_bidder_code)

                # 1. Lấy dữ liệu thô từ dòng hiện tại
                curr_bid = self.clean_money(self.get_val(row, ["giá dự thầu"]))
                curr_win = self.clean_money(self.get_val(row, ["giá trúng thầu"]))
                curr_jv = self.get_val(row, ["tên liên danh"])
                
                # 2. Cập nhật Bộ nhớ Tạm (Nếu dòng này có dữ liệu -> Nó là dòng mới/Leader)
                if curr_win > 0:
                    shared_data["win_price"] = curr_win
                    shared_data["bid_price"] = curr_bid
                    shared_data["eval_price"] = self.clean_money(self.get_val(row, ["giá đánh giá"]))
                    shared_data["correct_price"] = self.clean_money(self.get_val(row, ["hiệu chỉnh"]))
                    shared_data["tech_score"] = self.get_val(row, ["điểm kỹ thuật"])
                    shared_data["exec_time"] = self.get_val(row, ["thời gian thực hiện gói thầu"])
                    shared_data["contract_time"] = self.get_val(row, ["thời gian thực hiện hợp đồng"])
                    shared_data["other"] = self.get_val(row, ["nội dung khác"])
                
                if curr_jv:
                    shared_data["jv_name"] = curr_jv

                # 3. Tạo Item (Dùng dữ liệu từ Bộ nhớ Tạm cho các trường Chung)
                item = {
                    # --- DỮ LIỆU RIÊNG (Luôn lấy từ dòng hiện tại) ---
                    "bidder_code": raw_bidder_code,
                    "tax_code": final_tax_code, # <-- Dùng biến đã xử lý
                    "bidder_name": b_name,
                    
                    # --- DỮ LIỆU CHUNG (Lấy từ Shared Data) ---
                    "role": shared_data["jv_name"], # Tên Liên Danh
                    
                    "bid_price": shared_data["bid_price"],
                    "winning_price": shared_data["win_price"],
                    "evaluated_price": shared_data["eval_price"],
                    "corrected_price": shared_data["correct_price"],
                    
                    "technical_score": shared_data["tech_score"],
                    "execution_time": shared_data["exec_time"],
                    "contract_period": shared_data["contract_time"],
                    "other_content": shared_data["other"]
                }
                winners_list.append(item)

        except Exception as e:
            logger.warning(f"Error Winners: {e}")
        return winners_list

    # --- 3. CÀO FAILED (LOGIC FILL-DOWN TƯƠNG TỰ) ---
    def scrape_failed(self, driver):
        failed_list = []
        try:
            xpath = "//div[contains(text(), 'Thông tin Nhà thầu không được lựa chọn')]/ancestor::div[contains(@class,'card')]//table"
            try: table = driver.find_element(By.XPATH, xpath)
            except: return []

            flat_rows = self.parse_html_table_with_rowspan(table)
            
            shared_reason = None
            shared_jv = None

            for row in flat_rows:
                b_name = self.get_val(row, ["tên nhà thầu"])
                if not b_name: continue
                # --- [UPDATE] XỬ LÝ MÃ SỐ THUẾ TẠI ĐÂY ---
                raw_bidder_code = self.get_val(row, ["mã định danh"])
                raw_tax_code = self.get_val(row, ["mã số thuế"])
                
                final_tax_code = self.clean_tax_code_logic(raw_tax_code, raw_bidder_code)

                curr_reason = self.get_val(row, ["lý do"])
                curr_jv = self.get_val(row, ["tên liên danh"])

                if curr_reason: shared_reason = curr_reason
                if curr_jv: shared_jv = curr_jv

                failed_list.append({
                    "bidder_code": raw_bidder_code,
                    "tax_code": final_tax_code, # <-- Dùng biến đã xử lý
                    "bidder_name": b_name,
                    "joint_venture_name": shared_jv, # Dữ liệu Chung
                    "reason": shared_reason          # Dữ liệu Chung
                })
        except: pass
        return failed_list

    # --- 6. SCRAPE ITEMS (FIXED: Removing "Total" lines) ---
    def scrape_items(self, driver):
        items_list = []
        try:
            # Try multiple XPaths to find the Goods table
            xpaths = [
                "//th[contains(text(), 'Danh mục hàng hóa')]/ancestor::table",
                "//div[contains(text(), 'Danh mục hàng hóa')]/ancestor::div[contains(@class,'card')]//table",
                "//div[contains(text(), 'Bảng giá trúng thầu của hàng hóa')]/ancestor::div[contains(@class,'card')]//table"
            ]
            table = None
            for xp in xpaths:
                try: 
                    table = driver.find_element(By.XPATH, xp)
                    if table: break
                except: continue
            
            if not table: return []

            headers = table.find_elements(By.XPATH, ".//thead//th | .//thead//td")
            col_map = {
                "name": ["danh mục hàng hóa", "tên hàng hóa"],
                "model": ["ký mã hiệu"],
                "brand": ["nhãn hiệu"],
                "year": ["năm sản xuất"],
                "origin": ["xuất xứ"],
                "manu": ["hãng sản xuất"],
                "specs": ["cấu hình", "kỹ thuật"]
            }
            indices = self.get_column_indices(headers, col_map)
            
            rows = table.find_elements(By.XPATH, ".//tbody/tr")
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                if not cells: continue
                
                name = self.get_cell_text(cells, indices.get("name"))
                if not name: continue
                
                # FILTER: Remove lines that are just numbers (e.g. Total Price)
                # Regex matches strings containing only digits, dots, commas, spaces
                if re.match(r'^[\d\.,\s]+$', name): continue
                if "tổng cộng" in name.lower(): continue

                items_list.append({
                    "item_name": name,
                    "model": self.get_cell_text(cells, indices.get("model")),
                    "brand": self.get_cell_text(cells, indices.get("brand")),
                    "year_of_manufacture": self.get_cell_text(cells, indices.get("year")),
                    "origin": self.get_cell_text(cells, indices.get("origin")),
                    "manufacturer": self.get_cell_text(cells, indices.get("manu")),
                    "technical_specs": self.get_cell_text(cells, indices.get("specs"))
                })
        except: pass
        return items_list

    # --- SAVE LOGIC ---
    def save_full_result(self, hsmt_id, general_info, winners_list, failed_list, items_list):
        try:
            self.db.query(BiddingResult).filter_by(hsmt_id=hsmt_id).delete()
            
            result = BiddingResult(
                hsmt_id=hsmt_id,
                result_status=general_info.get("result_status"),
                posting_date=general_info.get("posting_date"),
                approved_budget=general_info.get("approved_budget"),
                package_price=general_info.get("package_price"),
                approval_date=general_info.get("approval_date"),
                approving_agency=general_info.get("approving_agency"),
                decision_number=general_info.get("decision_number"),
                decision_link=general_info.get("decision_link"),
                ehsdt_report_link=general_info.get("ehsdt_report_link"),
                bidding_result_text=general_info.get("bidding_result_text")
            )
            self.db.add(result)
            self.db.commit()
            self.db.refresh(result)
            
            for w in winners_list:
                winner = BiddingResultWinner(
                    result_id=result.id,
                    bidder_code=w['bidder_code'],
                    tax_code=w['tax_code'],
                    bidder_name=w['bidder_name'],
                    role=w['role'], # Tên Liên danh
                    
                    # Dữ liệu này giờ đã được fill-down cho tất cả thành viên
                    bid_price=w['bid_price'],
                    winning_price=w['winning_price'],
                    evaluated_price=w['evaluated_price'],
                    corrected_price=w['corrected_price'],
                    
                    technical_score=w['technical_score'],
                    execution_time=w['execution_time'],
                    contract_period=w['contract_period'],
                    other_content=w['other_content']
                )
                self.db.add(winner)

            for f in failed_list:
                fail = BiddingResultFailed(
                    result_id=result.id,
                    bidder_code=f['bidder_code'],
                    tax_code=f['tax_code'],
                    bidder_name=f['bidder_name'],
                    joint_venture_name=f['joint_venture_name'],
                    reason=f['reason']
                )
                self.db.add(fail)
            
            for i in items_list:
                item = BiddingResultItem(
                    result_id=result.id,
                    item_name=i.get('item_name'),
                    model=i.get('model'),
                    brand=i.get('brand'),
                    year_of_manufacture=i.get('year_of_manufacture'),
                    origin=i.get('origin'),
                    manufacturer=i.get('manufacturer'),
                    technical_specs=i.get('technical_specs')
                )
                self.db.add(item)

            pkg = self.db.query(BiddingPackage).filter_by(hsmt_id=hsmt_id).first()
            if pkg:
                pkg.trang_thai = PackageStatus.CLOSED
                if winners_list:
                    pkg.nha_thau_trung_thau = "; ".join([w['bidder_name'] for w in winners_list if w['bidder_name']])
                    prices = [w['winning_price'] for w in winners_list if w['winning_price'] > 0]
                    pkg.gia_trung_thau = max(prices) if prices else 0
            
            self.db.commit()
            logger.info(f"✅ Saved Package {hsmt_id} | Winners: {len(winners_list)} | Failed: {len(failed_list)} | Items: {len(items_list)}")

        except Exception as e:
            self.db.rollback()
            logger.error(f"DB Save Error: {e}")

    # --- MAIN FLOW ---
    def search_and_process(self, driver, pkg):
        try:
            url_search = "https://muasamcong.mpi.gov.vn/web/guest/contractor-selection?p_p_id=egpportalcontractorselectionv2_WAR_egpportalcontractorselectionv2&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view&_egpportalcontractorselectionv2_WAR_egpportalcontractorselectionv2_render=search"
            driver.get(url_search)
            driver.execute_script("document.body.style.zoom='70%'")
            time.sleep(2) 
            
            # Search
            try:
                inp = WebDriverWait(driver, 15).until(EC.visibility_of_element_located((By.XPATH, "//input[contains(@placeholder, 'TBMT') or contains(@placeholder, 'Tên gói thầu')]")))
                inp.click(); inp.send_keys(Keys.CONTROL + "a"); inp.send_keys(Keys.DELETE); inp.send_keys(pkg.ma_tbmt); time.sleep(1); inp.send_keys(Keys.ENTER)
            except:
                logger.error(f"Gói {pkg.ma_tbmt}: Search box not found."); return

            time.sleep(5)
            
            # Check Results
            results = driver.find_elements(By.XPATH, "//*[contains(text(), 'Có nhà thầu trúng thầu')]")
            if len(results) > 0:
                logger.info(f"-> Gói {pkg.ma_tbmt}: CÓ KẾT QUẢ. Đang vào chi tiết...")
                opened = False
                try:
                    detail_link = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, f"//a[contains(text(), '{pkg.ma_tbmt}')]")))
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", detail_link)
                    driver.execute_script("arguments[0].click();", detail_link)
                    opened = True
                except:
                    try:
                        detail_link = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//a[contains(@href, 'notify-contractor')]")))
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", detail_link)
                        driver.execute_script("arguments[0].click();", detail_link)
                        opened = True
                    except: pass
                
                if not opened: logger.error("❌ Không mở được chi tiết gói thầu."); return

                time.sleep(5)
                
                # Switch Tab
                tab_xpaths = ["//a[contains(text(), 'Kết quả lựa chọn nhà thầu')]", "//div[contains(text(), 'Kết quả lựa chọn nhà thầu')]", "//li[contains(text(), 'Kết quả lựa chọn nhà thầu')]"]
                clicked = False
                for xp in tab_xpaths:
                    try:
                        tab = driver.find_element(By.XPATH, xp)
                        if tab.is_displayed():
                            driver.execute_script("arguments[0].click();", tab); clicked=True; break
                    except: continue
                if not clicked: logger.warning("Không click được Tab KQ"); return

                time.sleep(3)
                
                # SCRAPE
                general_info = self.scrape_general_info(driver)
                winners = self.scrape_winners(driver)
                failed = self.scrape_failed(driver)
                items = self.scrape_items(driver)
                
                self.save_full_result(pkg.hsmt_id, general_info, winners, failed, items)
            else:
                logger.info(f"-> Gói {pkg.ma_tbmt}: Chưa có KQ hiển thị.")

        except Exception as e:
            logger.error(f"Processing Error {pkg.ma_tbmt}: {str(e)}")

    # def run(self):
    #     pkgs = self.db.query(models.BiddingPackage).filter(models.BiddingPackage.trang_thai == models.PackageStatus.SUBMITTED).all()
    #     logger.info(f"Found {len(pkgs)} SUBMITTED packages.")
    #     for index, pkg in enumerate(pkgs):
    #         driver = self.start_driver()
    #         if not driver: continue
    #         try:
    #             self.search_and_process(driver, pkg)
    #         finally:
    #             driver.quit()
    #             time.sleep(2)
    # Sửa lại hàm run() trong ResultCrawlerBot
    def run(self):
        pkgs = self.db.query(BiddingPackage).filter(
            BiddingPackage.trang_thai == PackageStatus.SUBMITTED
        ).all()
        
        logger.info(f"Found {len(pkgs)} SUBMITTED packages.")
        if not pkgs: return

        # 1. Khởi động driver lần đầu
        driver = self.start_driver()
        
        # [QUAN TRỌNG] Nếu ngay từ đầu đã không bật được thì dừng luôn
        if not driver: 
            logger.error("❌ Không khởi động được Driver ngay từ đầu. Dừng Bot.")
            return

        try:
            for index, pkg in enumerate(pkgs):
                logger.info(f"Processing {index + 1}/{len(pkgs)}: {pkg.ma_tbmt}")
                
                # Kiểm tra lại driver trước khi dùng (đề phòng vòng lặp trước làm driver thành None)
                if not driver:
                    logger.warning("⚠️ Driver đang bị None, đang thử khởi động lại...")
                    driver = self.start_driver()
                    if not driver:
                        logger.error("❌ Khởi động lại thất bại. Bỏ qua gói này.")
                        continue # Bỏ qua gói này, thử gói sau

                try:
                    self.search_and_process(driver, pkg)
                except Exception as e:
                    logger.error(f"Error processing {pkg.ma_tbmt}: {e}")
                    
                    # Cơ chế Reset Driver khi gặp lỗi nặng
                    try:
                        if driver: # Kiểm tra trước khi quit
                            driver.quit()
                    except: pass
                    
                    # Khởi động lại driver mới cho vòng lặp tiếp theo
                    logger.info("🔄 Đang khởi động lại Driver mới do lỗi...")
                    driver = self.start_driver() 

        finally:
            # [FIX LỖI CỦA BẠN TẠI ĐÂY]
            # Chỉ gọi quit() nếu driver KHÔNG PHẢI LÀ None
            if driver is not None:
                try:
                    driver.quit()
                except Exception as e:
                    logger.warning(f"Lỗi khi đóng driver: {e}")
            
            logger.info("Done processing all packages.")
if __name__ == "__main__":
    bot = ResultCrawlerBot()
    bot.run()