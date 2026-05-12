import json
import os
import urllib3
import ssl
import requests
import random
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==============================================================================
# PHẦN 0: CẤU HÌNH XOAY VÒNG (ROTATION) ĐỂ TÀNG HÌNH TRÌNH DUYỆT
# ==============================================================================
# Danh sách User-Agent đa dạng (Windows, macOS, Linux)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/122.0.0.0"
]

# Tạm thời để trống vì chưa gắn Proxy thật. Nếu sau này có, anh thêm vào mảng này.
# Ví dụ: [{"server": "http://IP:PORT", "username": "user", "password": "pwd"}]
PROXIES = []

def get_random_context_options():
    """Hàm helper để sinh cấu hình ngẫu nhiên (Mặt nạ) cho mỗi phiên duyệt web"""
    options = {
        "accept_downloads": True,
        "user_agent": random.choice(USER_AGENTS)
    }
    if PROXIES:
        options["proxy"] = random.choice(PROXIES)
    return options

# ==============================================================================
# PHẦN 1: CÁC HÀM LÕI BÓC TÁCH DỮ LIỆU
# ==============================================================================
class LegacyCipherAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context()
        context.set_ciphers('DEFAULT:@SECLEVEL=1')
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = context
        return super(LegacyCipherAdapter, self).init_poolmanager(*args, **kwargs)

def format_date(date_str):
    if not date_str or date_str == "N/A": return "N/A"
    try:
        parts = date_str.split('T')
        d_parts = parts[0].split('-')
        t_parts = parts[1].split(':') if len(parts) > 1 else ["00", "00"]
        return f"{d_parts[2]}/{d_parts[1]}/{d_parts[0]} {t_parts[0]}:{t_parts[1]}"
    except: return date_str

def export_general_info_to_markdown(info_json, output_dir, trang_thai_ben_ngoai="N/A"):
    # [CẬP NHẬT] Thêm bidoNotifyContractorP vào danh sách quét block thông tin
    info_block = (
        info_json.get("bidoNotifyContractorM") or 
        info_json.get("bidoNotifyContractorP") or 
        info_json.get("bidNoContractorResponse", {}).get("bidNotification", {}) or
        info_json.get("notifyContractorM", {})
    )
    if not info_block:
        for k, v in info_json.items():
            if isinstance(v, dict) and "notifyNo" in v:
                info_block = v
                break

    if not info_block: return None
        
    offline_dto = info_json.get("bidInvContractorOfflineDTO", {}) or {}

    map_bid_form = {"DTRR": "Đấu thầu rộng rãi", "CHCT": "Chào hàng cạnh tranh", "CDT": "Chỉ định thầu"}
    map_contract = {"TG": "Trọn gói", "DGCD": "Đơn giá cố định", "DCDC": "Đơn giá điều chỉnh"}
    map_bid_mode = {"1_MTHS": "Một giai đoạn một túi hồ sơ", "1_MTHE": "Một giai đoạn hai túi hồ sơ", "1_HTHS": "Một giai đoạn hai túi hồ sơ"}
    map_plan_type = {"DTPT": "Chi đầu tư phát triển", "TX": "Chi thường xuyên"}
    map_invest_field = {"XL": "Xây lắp", "HH": "Hàng hóa", "TV": "Tư vấn", "PTV": "Phi tư vấn"}
    map_process = {"LDT": "Luật Đấu thầu/ Áp dụng Luật Đấu thầu", "KHAC": "Khác"}
    map_work_type = {"KHAC": "Khác", "CTGG": "Công trình giao thông"}

    notify_no = info_block.get("notifyNo", "N/A")
    public_date = format_date(info_block.get("publicDate", "N/A"))
    notify_version = info_block.get("notifyVersion", "00")
    plan_no = info_block.get("planNo", "N/A")
    plan_type_code = info_block.get("planType", "Khác")
    plan_type = map_plan_type.get(plan_type_code, plan_type_code)
    plan_name = info_block.get("planName", "N/A")
    process_apply_code = info_block.get("processApply", "N/A")
    process_apply = map_process.get(process_apply_code, process_apply_code)
    bid_name = info_block.get("bidName", "N/A")
    investor = info_block.get("investorName") or info_block.get("procuringEntityName", "N/A")
    capital_detail = info_block.get("capitalDetail", "N/A")
    invest_field_code = info_block.get("investField", "N/A")
    invest_field = map_invest_field.get(invest_field_code, invest_field_code)
    bid_form_code = info_block.get("bidForm", "N/A")
    bid_form = map_bid_form.get(bid_form_code, bid_form_code)
    contract_type_code = info_block.get("contractType", "N/A") # cType hoặc contractType
    if contract_type_code == "N/A": contract_type_code = info_block.get("cType", "N/A")
    contract_type = map_contract.get(contract_type_code, contract_type_code)
    is_domestic = "Trong nước" if str(info_block.get("isDomestic")) == "1" else "Quốc tế"
    bid_mode_code = info_block.get("bidMode", "N/A")
    bid_mode = map_bid_mode.get(bid_mode_code, bid_mode_code)
    
    contract_period_unit = str(info_block.get("contractPeriodUnit") or info_block.get("cPeriodUnit", "ngày")).replace("D", "ngày").replace("W", "tuần").replace("M", "tháng")
    contract_period_val = info_block.get('contractPeriod') or info_block.get('cPeriod', 'N/A')
    contract_period = f"{contract_period_val} {contract_period_unit}"
    
    is_multi_lot = "Có" if str(info_block.get("isMultiLot")) == "1" else "Không"
    bid_close_date = format_date(info_block.get("bidCloseDate", "N/A"))
    bid_open_date = format_date(info_block.get("bidOpenDate", "N/A"))
    bid_open_location = info_block.get("bidOpenLocation", "https://muasamcong.mpi.gov.vn")
    validity_unit = str(info_block.get("bidValidityPeriodUnit", "ngày")).replace("D", "ngày").replace("M", "tháng")
    validity = f"{info_block.get('bidValidityPeriod', 'N/A')} {validity_unit}"
    guarantee_value = info_block.get("guaranteeValue") or info_block.get("bidGuaranteeValue") or 0
    guarantee_form = info_block.get("guaranteeForm") or info_block.get("bidGuaranteeForm", "N/A")
    work_type_code = info_block.get("workType", "Khác")
    work_type = map_work_type.get(work_type_code, work_type_code)
    decision_no = offline_dto.get("decisionNo", "N/A")
    raw_decision_date = format_date(offline_dto.get("decisionDate", "N/A"))
    decision_date = raw_decision_date.split(" ")[0] if raw_decision_date != "N/A" else "N/A"
    decision_agency = offline_dto.get("decisionAgency", "N/A")

    # [CẬP NHẬT] Xử lý linh hoạt Hình thức dự thầu & Địa điểm nhận/phát hành
    is_internet_val = str(info_block.get("isInternet", "1"))
    hinh_thuc_du_thau = "Qua mạng" if is_internet_val == "1" else "Trực tiếp"
    
    if is_internet_val == "1":
        dia_diem_phat_hanh = "https://muasamcong.mpi.gov.vn"
        dia_diem_nhan = "https://muasamcong.mpi.gov.vn"
    else:
        dia_diem_phat_hanh = info_block.get("issueLocation") or offline_dto.get("issueLocation", "N/A")
        dia_diem_nhan = info_block.get("receiveLocation") or offline_dto.get("receiveLocation", "N/A")
    
    fee_val = info_block.get("receiveFee") or info_block.get("ebidFee") or info_block.get("hsdtFee")
    chi_phi_str = f"{int(fee_val):,.0f} VND".replace(",", ".") if fee_val is not None else "Theo HSMT"

    location_str = "N/A"
    
    loc_list_v2 = info_json.get("lsBidpBidLocationDTO") or info_json.get("bidpBidLocationList")
    if loc_list_v2 and isinstance(loc_list_v2, list):
        loc_names = []
        for loc in loc_list_v2:
            parts = []
            if loc.get("wardName"): parts.append(loc.get("wardName"))
            if loc.get("districtName"): parts.append(loc.get("districtName"))
            if loc.get("provName"): parts.append(loc.get("provName"))
            if parts: loc_names.append(", ".join(parts))
        if loc_names: location_str = " | ".join(loc_names)
        
    if location_str == "N/A":
        raw_location = info_block.get("location")
        if isinstance(raw_location, str) and raw_location.strip().startswith("["):
            try:
                loc_list = json.loads(raw_location)
                loc_names = []
                for loc in loc_list:
                    parts = []
                    if loc.get("wardName"): parts.append(loc.get("wardName"))
                    if loc.get("districtName"): parts.append(loc.get("districtName"))
                    if loc.get("provName"): parts.append(loc.get("provName"))
                    if parts: loc_names.append(", ".join(parts))
                    elif loc.get("address"): loc_names.append(loc.get("address"))
                if loc_names: location_str = " | ".join(loc_names)
            except: pass

    guarantee_note = " (Theo Điều 20 Nghị định 214/2025/NĐ-CP, nhà thầu...)" if guarantee_value and float(guarantee_value) > 0 else ""

    md_content = f"""# Thông báo mời thầu: {notify_no}

## Thông tin cơ bản
* **Mã TBMT:** {notify_no}
* **Trạng thái của gói thầu:** {trang_thai_ben_ngoai}
* **Ngày đăng tải:** {public_date}
* **Phiên bản thay đổi:** {notify_version}

## Thông tin chung của KHLCNT
* **Mã KHLCNT:** {plan_no}
* **Phân loại KHLCNT:** {plan_type}
* **Tên dự toán mua sắm:** {plan_name}

## Thông tin gói thầu
* **Quy trình áp dụng:** {process_apply}
* **Tên gói thầu:** {bid_name}
* **Chủ đầu tư:** {investor}
* **Chi tiết nguồn vốn:** {capital_detail}
* **Lĩnh vực:** {invest_field}
* **Hình thức lựa chọn nhà thầu:** {bid_form}
* **Loại hợp đồng:** {contract_type}
* **Trong nước/ Quốc tế:** {is_domestic}
* **Phương thức lựa chọn nhà thầu:** {bid_mode}
* **Thời gian thực hiện gói thầu:** {contract_period}
* **Gói thầu có nhiều phần/lô:** {is_multi_lot}

## Cách thức dự thầu
* **Hình thức dự thầu:** {hinh_thuc_du_thau}
* **Địa điểm phát hành e-HSMT / HSMT:** {dia_diem_phat_hanh}
* **Chi phí nộp HSDT:** {chi_phi_str}
* **Địa điểm nhận e-HSDT / HSDT:** {dia_diem_nhan}
* **Địa điểm thực hiện gói thầu:** {location_str}

## Thông tin dự thầu
* **Thời điểm đóng thầu:** {bid_close_date}
* **Thời điểm mở thầu:** {bid_open_date}
* **Địa điểm mở thầu:** {bid_open_location}
* **Hiệu lực hồ sơ dự thầu:** {validity}
* **Số tiền bảo đảm dự thầu:** {float(guarantee_value):,.0f} VND{guarantee_note} if guarantee_value else 'Theo HSMT'
* **Hình thức bảo đảm dự thầu:** {guarantee_form}
* **Loại công trình:** {work_type}

## Thông tin quyết định phê duyệt
* **Số quyết định phê duyệt:** {decision_no}
* **Ngày phê duyệt:** {decision_date}
* **Cơ quan ban hành quyết định:** {decision_agency}
"""
    bid_dir = os.path.join(output_dir, notify_no)
    os.makedirs(bid_dir, exist_ok=True)
    md_filepath = os.path.join(bid_dir, f"ThongTin_{notify_no}.md")
    with open(md_filepath, "w", encoding="utf-8") as f: f.write(md_content)
    print(f"      ✅ Đã tạo Markdown: ThongTin_{notify_no}.md")
    return bid_dir

def extract_files_from_jsons(info_json, hsmt_json):
    files_map = {}
    
    def extract_from_form_value(form_str):
        try:
            data = json.loads(form_str)
            shared = data.get("sharedFiles", [])
            
            explicit_uuids = set()
            def find_explicit_uuids(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if isinstance(v, str) and len(v) > 20 and '-' in v and v != "id":
                            explicit_uuids.add(v)
                    for v in obj.values():
                        if isinstance(v, (dict, list)): find_explicit_uuids(v)
                elif isinstance(obj, list):
                    for item in obj:
                        if isinstance(item, (dict, list)): find_explicit_uuids(item)
            
            find_explicit_uuids(data)
            available_shared = [x for x in shared if x not in explicit_uuids]
            shared_idx = 0
            
            def walk(obj):
                nonlocal shared_idx
                if isinstance(obj, dict):
                    for k, v in list(obj.items()):
                        if v == "id" and shared_idx < len(available_shared):
                            obj[k] = available_shared[shared_idx]
                            shared_idx += 1
                    
                    fname = None
                    for k, v in obj.items():
                        if isinstance(v, str) and "." in v:
                            ext = v.split('.')[-1].lower()
                            if ext in ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'rar', 'zip', 'dwg', 'cad', '7z', 'jpg', 'png']:
                                fname = v
                                break
                    
                    if fname:
                        fid = None
                        for k, v in obj.items():
                            if 'id' in k.lower() and isinstance(v, str) and len(v) > 15 and v != "id":
                                fid = v
                                break
                        if not fid:
                            for k, v in obj.items():
                                if isinstance(v, str) and len(v) > 20 and '-' in v:
                                    fid = v
                                    break
                        
                        if fid:
                            files_map[fid] = fname

                    for v in obj.values():
                        if isinstance(v, (dict, list)): walk(v)
                        
                elif isinstance(obj, list):
                    for item in obj:
                        if isinstance(item, (dict, list)): walk(item)
            
            walk(data)
        except Exception as e:
            pass

    if hsmt_json and "bidoInvBiddingDTO" in hsmt_json:
        for item in hsmt_json["bidoInvBiddingDTO"]:
            if item.get("formValue"): extract_from_form_value(item["formValue"])

    for j_data in [info_json, hsmt_json]:
        if not j_data: continue
        off = j_data.get("bidInvContractorOfflineDTO", {})
        if off:
            if off.get("decisionFileId"): files_map[off.get("decisionFileId")] = off.get("decisionFileName", "Quyet_dinh.pdf")
            if off.get("briefFileId"): files_map[off.get("briefFileId")] = off.get("briefFileName", "Tom_tat.pdf")

    return [{"id": k, "name": v} for k, v in files_map.items()]

# ==============================================================================
# PHẦN 2: XỬ LÝ TỪNG GÓI THẦU
# ==============================================================================
def process_single_bid(browser, task, global_output_dir):
    url = task['url']
    trang_thai = task.get('status', 'N/A')
    
    # [CẬP NHẬT] Đã gắn Context xoay vòng IP/Browser vào mỗi Tab con
    context_options = get_random_context_options()
    context = browser.new_context(**context_options)
    
    page = context.new_page()
    
    extracted_data = {"info_json": None, "hsmt_json": None, "url_token": None, "bearer_token": None}
    bid_dir = global_output_dir
    
    info_json = None 
    hsmt_json = None

    def sniff_request(request):
        auth_header = request.headers.get("authorization")
        if auth_header and "Bearer" in auth_header:
            extracted_data["bearer_token"] = auth_header

    def sniff_response(response):
        try:
            url_str = response.url
            if any(x in url_str for x in ["/lcnt_tbmt_ttc_ldt", "notify-contractor/find-by-id", "notify-contractor/find-by-notify-no"]):
                extracted_data["info_json"] = response.json()
                
            if any(x in url_str for x in ["/lcnt_tbmt_hsmt", "inv-bidding/find-by-id", "inv-bidding/find-by-notify-id"]):
                extracted_data["hsmt_json"] = response.json()
                
            parsed_url = urlparse(url_str)
            t_list = parse_qs(parsed_url.query).get('token')
            if t_list and not extracted_data["url_token"]:
                extracted_data["url_token"] = str(t_list[0])
        except: pass

    page.on("request", sniff_request)
    page.on("response", sniff_response)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000) 
        
        # [CẬP NHẬT] Áp dụng Random Delay (từ 3 đến 6 giây) thay vì fix cứng 4s
        page.wait_for_timeout(random.randint(3000, 6000)) 
        
        try:
            page.locator("text='Hồ sơ mời thầu'").first.click(timeout=5000)
            page.wait_for_timeout(random.randint(2000, 3500))
        except: pass

        info_json = extracted_data.get("info_json")
        if info_json:
            created_dir = export_general_info_to_markdown(info_json, global_output_dir, trang_thai)
            if created_dir: bid_dir = created_dir

        # ---------------------------------------------------------
        # TẢI BIỂU MẪU WEBFORM
        # ---------------------------------------------------------
        try:
            webform_btn = page.locator("text='Tải tất cả biểu mẫu webform'").first
            if webform_btn.is_visible(timeout=3000):
                print(f"      [*] Đang tải E-HSMT từ nút 'Tải tất cả biểu mẫu webform'...")
                with context.expect_page(timeout=15000) as new_page_info:
                    webform_btn.click()
                
                try:
                    viewer_page = new_page_info.value
                    viewer_page.wait_for_load_state("domcontentloaded")
                    
                    dl_btn = viewer_page.locator("button.btn-primary:has-text('Tải về')").first
                    dl_btn.wait_for(state="visible", timeout=15000)
                    viewer_page.wait_for_timeout(3000)
                    
                    with viewer_page.expect_download(timeout=45000) as download_info:
                        try:
                            dl_btn.click(force=True, timeout=5000)
                        except:
                            viewer_page.evaluate("document.querySelector('button.btn-primary').click()")
                            
                    download = download_info.value
                    webform_save_path = os.path.join(bid_dir, download.suggested_filename)
                    download.save_as(webform_save_path)
                    print(f"      ✅ Đã tải xong Webform: {download.suggested_filename}")
                except Exception as e:
                    print(f"      [-] Bỏ qua tải Webform: Server quá tải không gen được file.")
                finally:
                    viewer_page.close() 
        except Exception as e:
            pass
            
    except Exception as e:
        print(f"      [!] Lỗi xử lý giao diện: {e}")
    finally:
        context.close()
        print("      [+] Đã đóng Tab UI, giải phóng RAM.")

    # --- ĐÃ VÔ HIỆU HÓA: TẢI FILE ĐÍNH KÈM TĨNH QUA API THEO YÊU CẦU ---
    # hsmt_json = extracted_data.get("hsmt_json")
    # url_token = extracted_data.get("url_token", "")
    # bearer_token = extracted_data.get("bearer_token")
    # if not info_json or not hsmt_json:
    #     print("      [!] CẢNH BÁO: Không bắt được gói dữ liệu API của trang này. Gói thầu bị bỏ qua!")
    #     return
    # files = extract_files_from_jsons(info_json, hsmt_json)
    # ...

# ==============================================================================
# PHẦN 3: ĐIỀU KHIỂN CHUNG - GOM LINK
# ==============================================================================
def master_search_and_crawl(linh_vuc, gia_tu, gia_den):
    OUTPUT_DIR = os.path.join(os.getcwd(), "MSC_Downloads")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("\n🚀 KHỞI ĐỘNG CRAWLER MUA SẮM CÔNG...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False) 
        
        # [CẬP NHẬT] Đã gắn Context xoay vòng IP/Browser vào phiên khởi tạo Search
        context_options = get_random_context_options()
        context = browser.new_context(**context_options)
        
        page = context.new_page()

        tasks = []

        try:
            print("[*] Đang truy cập và Mở form Tìm kiếm nâng cao...")
            page.goto("https://muasamcong.mpi.gov.vn/", wait_until="domcontentloaded")
            
            page.evaluate("""
                var p = document.getElementById('notification-popup-v2'); if(p) p.remove();
                var b = document.querySelector('.modal-backdrop'); if(b) b.remove();
                var p2 = document.querySelector('.notification-popup'); if(p2) p2.remove();
            """)
            
            page.locator("a:has-text('Tìm kiếm nâng cao'), button:has-text('Tìm kiếm nâng cao')").first.click(timeout=5000)
            page.wait_for_selector(f"text='{linh_vuc}'", timeout=10000)

            print(f"[*] Điền tiêu chí tìm kiếm...")
            page.locator(f"label:has-text('{linh_vuc}')").first.click()
            page.locator("input[placeholder='Từ']").fill(str(gia_tu))
            page.locator("input[placeholder='Đến']").fill(str(gia_den))
            
            print("[*] Đang gửi yêu cầu tìm kiếm...")
            page.locator("button:has-text('Tìm kiếm')").last.click()
            
            print("[*] Đang đợi hệ thống nặn dữ liệu (Bỏ qua tracker ngầm)...")
            page.wait_for_timeout(3000) 
            
            page.wait_for_selector("a[href*='stepCode=notify']", state="visible", timeout=40000)

            print("   [-] Đang mở rộng danh sách lên 50 gói thầu/trang...")
            try:
                page.locator("select").last.select_option("50")
                page.wait_for_timeout(5000) 
            except Exception as e:
                print(f"   [!] Không thể đổi sang 50 gói, tiếp tục lấy số lượng mặc định. Lỗi: {e}")

            print("   [-] Đã thấy kết quả! Đang cuộn trang để lấy toàn bộ dữ liệu...")
            page.evaluate("""
                let totalHeight = 0; let distance = 500;
                let timer = setInterval(() => {
                    window.scrollBy(0, distance); totalHeight += distance;
                    if(totalHeight >= document.body.scrollHeight) clearInterval(timer);
                }, 400);
            """)
            page.wait_for_timeout(8000)

            print("   [-] Đang bốc dữ liệu Link và Trạng thái...")
            cards = page.locator("div.content__body__left__item__infor").all()
            
            for card in cards:
                link_el = card.locator("a[href*='stepCode=notify']").first
                if link_el.is_visible():
                    href = link_el.get_attribute("href")
                    title = link_el.inner_text().strip()
                    
                    status_el = card.locator("span[class*='notice']").first
                    status_text = status_el.inner_text().strip() if status_el.is_visible() else "N/A"

                    if href:
                        full_url = href if href.startswith("http") else f"https://muasamcong.mpi.gov.vn{href}"
                        if not any(t['url'] == full_url for t in tasks):
                            tasks.append({
                                "url": full_url, 
                                "title": title if title else "Gói thầu",
                                "status": status_text
                            })
                
                if len(tasks) >= 50: break

            if len(tasks) == 0:
                print("[!] Không tìm thấy kết quả.")
                return

            print(f"[+] Thu thập thành công {len(tasks)} gói thầu vào hàng chờ.\n")
            
            context.close()

            for i, task in enumerate(tasks, start=1):
                print(f"==================================================")
                print(f" BẮT ĐẦU XỬ LÝ GÓI [{i}/{len(tasks)}]: {task['title']} - Trạng thái: {task['status']}")
                print(f"==================================================")
                
                process_single_bid(browser, task, OUTPUT_DIR)

        except Exception as e:
            print(f"[!] Lỗi ở luồng điều khiển chính: {e}")
        finally:
            print("\n🎉 HOÀN TẤT TOÀN BỘ TIẾN TRÌNH!")
            browser.close()

if __name__ == "__main__":
    LINH_VUC = "Xây lắp"
    GIA_TU = "1000000000"  # 1 tỷ
    GIA_DEN = "5000000000" # 5 tỷ
    master_search_and_crawl(LINH_VUC, GIA_TU, GIA_DEN)