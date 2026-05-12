import sys
import os
import io
import re
import json
import time
import random
import logging
import mimetypes
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.infrastructure.database.database import SessionLocal
import app.infrastructure.database.all_models  # noqa: F401 - đăng ký toàn bộ model với SQLAlchemy
from app.modules.crawler_config.model import CrawlLog, CrawlRule, CrawlSchedule
from app.modules.bidding.package.model import BiddingPackage, BiddingPackageFile
from app.core.utils.enum import PackageStatus
from app.infrastructure.storage.minio_client import MinIOHandler

from playwright.sync_api import sync_playwright
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

try:
    sys.stdout.reconfigure(encoding='utf-8')  # type: ignore
except AttributeError:
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PC1_Bot")

# ==============================================================================
# CẤU HÌNH CHỐNG PHÁT HIỆN
# ==============================================================================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

# ==============================================================================
# MAPS — giá trị code → tên tiếng Việt
# ==============================================================================
MAP_BID_FORM    = {"DTRR": "Đấu thầu rộng rãi", "CHCT": "Chào hàng cạnh tranh", "CDT": "Chỉ định thầu"}
MAP_CONTRACT    = {"TG": "Trọn gói", "DGCD": "Đơn giá cố định", "DCDC": "Đơn giá điều chỉnh"}
MAP_BID_MODE    = {"1_MTHS": "Một giai đoạn một túi hồ sơ", "1_MTHE": "Một giai đoạn hai túi hồ sơ", "1_HTHS": "Một giai đoạn hai túi hồ sơ"}
MAP_PLAN_TYPE   = {"DTPT": "Chi đầu tư phát triển", "TX": "Chi thường xuyên"}
MAP_INVEST_FIELD= {"XL": "Xây lắp", "HH": "Hàng hóa", "TV": "Tư vấn", "PTV": "Phi tư vấn", "HON_HOP": "Hỗn hợp"}
MAP_PROCESS     = {"LDT": "Luật Đấu thầu/ Áp dụng Luật Đấu thầu", "KHAC": "Khác"}
MAP_WORK_TYPE   = {"KHAC": "Khác", "CTGG": "Công trình giao thông"}


class MuasamcongDBBot:
    def __init__(self):
        self.minio = MinIOHandler()
        self.download_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
        os.makedirs(self.download_dir, exist_ok=True)

        try:
            self.db: Session = SessionLocal()
            self.db.execute(text("SELECT 1"))
            logger.info("-> Kết nối Database thành công!")
        except Exception as e:
            logger.error(f"-> LỖI KẾT NỐI DATABASE: {e}")
            sys.exit(1)

    # ---------------------------------------------------------
    # HELPERS
    # ---------------------------------------------------------
    def _sanitize(self, filename: str) -> str:
        return re.sub(r'[\\/*?:"<>|]', '_', filename).strip()

    def _parse_iso_date(self, date_str) -> datetime | None:
        """Parse ISO date từ API (VD: '2025-03-15T10:30:00') → datetime"""
        if not date_str or date_str == "N/A":
            return None
        try:
            parts = str(date_str).split('T')
            d = parts[0].split('-')
            t = parts[1].split(':') if len(parts) > 1 else ["00", "00"]
            return datetime.strptime(f"{d[2]}/{d[1]}/{d[0]} {t[0]}:{t[1]}", "%d/%m/%Y %H:%M")
        except:
            return None

    def _get_info_block(self, info_json: dict) -> dict:
        """Lấy block dữ liệu chính từ JSON API (hỗ trợ nhiều cấu trúc khác nhau)"""
        block = (
            info_json.get("bidoNotifyContractorM") or
            info_json.get("bidoNotifyContractorP") or
            info_json.get("bidNoContractorResponse", {}).get("bidNotification", {}) or
            info_json.get("notifyContractorM", {})
        )
        if not block:
            for v in info_json.values():
                if isinstance(v, dict) and "notifyNo" in v:
                    return v
        return block or {}

    def _extract_location(self, info_json: dict, info_block: dict) -> str | None:
        loc_list = info_json.get("lsBidpBidLocationDTO") or info_json.get("bidpBidLocationList")
        if loc_list and isinstance(loc_list, list):
            parts = []
            for loc in loc_list:
                seg = [loc.get(k) for k in ("wardName", "districtName", "provName") if loc.get(k)]
                if seg:
                    parts.append(", ".join(seg))
            if parts:
                return " | ".join(parts)

        raw = info_block.get("location")
        if isinstance(raw, str) and raw.strip().startswith("["):
            try:
                for loc in json.loads(raw):
                    seg = [loc.get(k) for k in ("wardName", "districtName", "provName") if loc.get(k)]
                    if seg:
                        return ", ".join(seg)
                    if loc.get("address"):
                        return loc["address"]
            except:
                pass
        return None

    def build_tbmt_data(self, info_json: dict, current_url: str) -> dict | None:
        """Map dữ liệu JSON API → dict chuẩn để lưu vào bảng bidding_packages"""
        b = self._get_info_block(info_json)
        if not b or not b.get("notifyNo"):
            return None

        offline = info_json.get("bidInvContractorOfflineDTO") or {}

        # Thời gian thực hiện
        p_unit = str(b.get("contractPeriodUnit") or b.get("cPeriodUnit", "ngày"))\
            .replace("D", "ngày").replace("W", "tuần").replace("M", "tháng")
        p_val = b.get("contractPeriod") or b.get("cPeriod")
        contract_period = f"{p_val} {p_unit}".strip() if p_val else None

        # Hiệu lực HSDT
        v_unit = str(b.get("bidValidityPeriodUnit", "ngày")).replace("D", "ngày").replace("M", "tháng")
        v_val = b.get("bidValidityPeriod")
        validity = f"{v_val} {v_unit}".strip() if v_val else None

        # Hình thức dự thầu & địa điểm
        is_internet = str(b.get("isInternet", "1")) == "1"
        if is_internet:
            dia_phat_hanh = "https://muasamcong.mpi.gov.vn"
            dia_nhan      = "https://muasamcong.mpi.gov.vn"
        else:
            dia_phat_hanh = b.get("issueLocation") or offline.get("issueLocation")
            dia_nhan      = b.get("receiveLocation") or offline.get("receiveLocation")

        fee = b.get("receiveFee") or b.get("ebidFee") or b.get("hsdtFee")
        ctype = b.get("contractType") or b.get("cType")

        return {
            "ma_tbmt":                          b.get("notifyNo"),
            "duong_dan_goi_thau":               current_url,
            "phien_ban_thay_doi":               str(b.get("notifyVersion", "00")).zfill(2),
            "ngay_dang_tai":                    self._parse_iso_date(b.get("publicDate")),
            "ma_khlcnt":                        b.get("planNo"),
            "phan_loai_khlcnt":                 MAP_PLAN_TYPE.get(b.get("planType", ""), b.get("planType")),
            "ten_du_an":                        b.get("planName"),
            "quy_trinh_ap_dung":                MAP_PROCESS.get(b.get("processApply", ""), b.get("processApply")),
            "ten_goi_thau":                     b.get("bidName"),
            "chu_dau_tu":                       b.get("investorName") or b.get("procuringEntityName"),
            "chi_tiet_nguon_von":               b.get("capitalDetail"),
            "linh_vuc":                         MAP_INVEST_FIELD.get(b.get("investField", ""), b.get("investField")),
            "hinh_thuc_lua_chon_nha_thau":      MAP_BID_FORM.get(b.get("bidForm", ""), b.get("bidForm")),
            "loai_hop_dong":                    MAP_CONTRACT.get(ctype or "", ctype),
            "trong_nuoc_hoac_quoc_te":          "Trong nước" if str(b.get("isDomestic")) == "1" else "Quốc tế",
            "phuong_thuc_lua_chon_nha_thau":    MAP_BID_MODE.get(b.get("bidMode", ""), b.get("bidMode")),
            "thoi_gian_thuc_hien_goi_thau":     contract_period,
            "goi_thau_co_nhieu_phan_lo":        "Có" if str(b.get("isMultiLot")) == "1" else "Không",
            "hinh_thuc_du_thau":                "Qua mạng" if is_internet else "Trực tiếp",
            "dia_diem_phat_hanh_e_hsmt":        dia_phat_hanh,
            "chi_phi_nop":                      float(fee) if fee is not None else 0.0,
            "dia_diem_nhan_e_hsdt":             dia_nhan,
            "dia_diem_thuc_hien_goi_thau":      self._extract_location(info_json, b),
            "thoi_diem_dong_thau":              self._parse_iso_date(b.get("bidCloseDate")),
            "thoi_diem_mo_thau":                self._parse_iso_date(b.get("bidOpenDate")),
            "dia_diem_mo_thau":                 b.get("bidOpenLocation"),
            "hieu_luc_hsdt":                    validity,
            "so_tien_dam_bao_du_thau":          float(b.get("guaranteeValue") or b.get("bidGuaranteeValue") or 0),
            "hinh_thuc_dam_bao_du_thau":        b.get("guaranteeForm") or b.get("bidGuaranteeForm"),
            "loai_cong_trinh":                  MAP_WORK_TYPE.get(b.get("workType", ""), b.get("workType")),
            "so_quyet_dinh_phe_duyet":          offline.get("decisionNo"),
            "ngay_phe_duyet":                   self._parse_iso_date(offline.get("decisionDate")),
            "co_quan_ban_hanh_quyet_dinh":      offline.get("decisionAgency"),
            "quyet_dinh_phe_duyet":             None,
            "trang_thai":                       PackageStatus.INTERESTED,
        }

    # ---------------------------------------------------------
    # DATABASE
    # ---------------------------------------------------------
    def create_crawl_log(self, rule_id):
        try:
            log = CrawlLog(rule_id=rule_id, start_time=datetime.now(), status="RUNNING", packages_found=0)
            self.db.add(log)
            self.db.commit()
            self.db.refresh(log)
            return log.id
        except Exception as e:
            logger.error(f"Lỗi tạo log: {e}")
            return None

    def update_crawl_log(self, log_id, status, count=0, failed=0, details=None, error=None):
        try:
            if not log_id:
                return
            log = self.db.query(CrawlLog).filter_by(id=log_id).first()
            if log:
                log.end_time = datetime.now()
                log.status = status
                log.packages_found = count
                log.packages_failed = failed
                log.details = json.dumps(details, ensure_ascii=False) if details else None
                log.error_message = str(error) if error else None
                self.db.commit()
        except Exception as e:
            logger.error(f"Lỗi update log: {e}")

    def save_package_to_db(self, data: dict) -> int | None:
        try:
            pkg = self.db.query(BiddingPackage).filter(BiddingPackage.ma_tbmt == data['ma_tbmt']).first()
            if not pkg:
                logger.info(f"-> [DB] INSERT: {data['ma_tbmt']}")
                pkg = BiddingPackage(**data)
                self.db.add(pkg)
            else:
                logger.info(f"-> [DB] UPDATE: {data['ma_tbmt']}")
                for k, v in data.items():
                    if v is not None:
                        setattr(pkg, k, v)
            self.db.commit()
            return pkg.hsmt_id
        except Exception as e:
            self.db.rollback()
            logger.error(f"Lỗi lưu TBMT: {e}")
            return None

    def _scrape_chi_phi_from_page(self, page) -> float:
        """Scrape chi phí nộp e-HSDT từ DOM vì API không trả về giá trị này."""
        KEYWORDS = ['Chi phí nộp e-HSDT', 'Chi phí nộp hồ sơ', 'Giá bán HSMT', 'Chi phí tham dự']

        # Bước 1 — Thử dùng Playwright locator trực tiếp (có wait tự động)
        try:
            for kw in KEYWORDS:
                # Tìm label chứa keyword, rồi lấy next sibling div
                label = page.locator(f"text={kw}").first
                if label.is_visible(timeout=3000):
                    # Thử lấy sibling kế tiếp
                    value_el = label.locator("xpath=following-sibling::div[1]")
                    if value_el.count() > 0:
                        raw = value_el.first.inner_text().strip()
                    else:
                        # Thử lấy div con của parent
                        raw = label.locator("xpath=../div[last()]").first.inner_text().strip()
                    if raw and re.search(r"\d", raw):
                        numeric = re.sub(r"[^\d]", "", raw.upper().replace("VND", "").replace("ĐỒNG", ""))
                        if numeric:
                            logger.info(f"-> [Playwright locator] Chi phí raw: '{raw}' → {numeric}")
                            return float(numeric)
        except Exception as e:
            logger.debug(f"-> Playwright locator fallback: {e}")

        # Bước 2 — Fallback: JS evaluate với nhiều selector strategy
        try:
            result: dict = page.evaluate("""
                () => {
                    const KEYWORDS = ['Chi phí nộp e-HSDT', 'Chi phí nộp hồ sơ', 'Giá bán HSMT', 'Chi phí tham dự'];
                    const debug = { tried_selectors: [], found_labels: [], result: '' };

                    // Strategy A: các selector class phổ biến
                    const SELECTORS = [
                        '.infomation__title',
                        '.information__title',
                        '[class*="infomation"][class*="title"]',
                        '[class*="information"][class*="title"]',
                        '.info-label', '.field-label', '.label',
                    ];

                    let labels = [];
                    for (const sel of SELECTORS) {
                        const found = document.querySelectorAll(sel);
                        debug.tried_selectors.push(sel + ':' + found.length);
                        if (found.length > 0 && labels.length === 0) {
                            labels = Array.from(found);
                        }
                    }

                    // Strategy B: nếu không tìm được qua class, tìm tất cả leaf nodes
                    if (labels.length === 0) {
                        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                        let node;
                        while ((node = walker.nextNode())) {
                            const text = node.textContent.trim();
                            if (KEYWORDS.some(kw => text.includes(kw))) {
                                labels.push(node.parentElement);
                            }
                        }
                        debug.tried_selectors.push('text_walker:' + labels.length);
                    }

                    for (const el of labels) {
                        const text = el.textContent.trim();
                        debug.found_labels.push(text.slice(0, 60));
                        if (!KEYWORDS.some(kw => text.includes(kw))) continue;

                        // Thử nextElementSibling
                        let sib = el.nextElementSibling;
                        while (sib) {
                            const val = sib.textContent.trim();
                            if (val && /\\d/.test(val)) { debug.result = val; return debug; }
                            sib = sib.nextElementSibling;
                        }

                        // Thử các con của parent (bỏ qua chính el)
                        const parent = el.parentElement;
                        if (parent) {
                            for (const child of parent.children) {
                                if (child === el) continue;
                                const val = child.textContent.trim();
                                if (val && /\\d/.test(val)) { debug.result = val; return debug; }
                            }
                        }
                    }
                    return debug;
                }
            """)

            if not isinstance(result, dict):
                result = {}
            logger.debug(f"-> [JS debug] tried={result.get('tried_selectors')}, labels={result.get('found_labels', [])[:5]}")

            raw = result.get("result", "")
            if raw and re.search(r"\d", raw):
                numeric = re.sub(r"[^\d]", "", raw.upper().replace("VND", "").replace("ĐỒNG", ""))
                if numeric:
                    logger.info(f"-> [JS evaluate] Chi phí raw: '{raw}' → {numeric}")
                    return float(numeric)
            else:
                logger.warning(f"-> [JS evaluate] Không tìm thấy chi phí. Labels tìm được: {result.get('found_labels', [])[:5]}")

        except Exception as e:
            logger.warning(f"-> Lỗi JS evaluate chi phí: {e}")

        return 0.0

    def update_file_path(self, ma_tbmt: str, file_path: str, file_name: str):
        try:
            pkg = self.db.query(BiddingPackage).filter_by(ma_tbmt=ma_tbmt).first()
            if not pkg:
                return
            existing = self.db.query(BiddingPackageFile).filter_by(
                hsmt_id=pkg.hsmt_id, file_name=file_name
            ).first()
            if existing:
                if existing.file_path != file_path:
                    existing.file_path = file_path
                    self.db.commit()
                return
            self.db.add(BiddingPackageFile(
                hsmt_id=pkg.hsmt_id,
                file_name=file_name,
                file_type="HSMT/Webform",
                file_path=file_path,
            ))
            self.db.commit()
        except Exception as e:
            logger.error(f"Lỗi update file: {e}")

    # ---------------------------------------------------------
    # XỬ LÝ 1 GÓI THẦU (Playwright + API sniffing)
    # ---------------------------------------------------------
    def process_package(self, url: str):
        """Mở URL bằng Playwright, sniff JSON API, lưu DB, tải webform, upload MinIO."""
        logger.info(f"--- Đang xử lý TBMT: {url} ---")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                accept_downloads=True,
            )
            page = context.new_page()
            sniffed: dict = {"info_json": None}

            def on_response(response):
                try:
                    u = response.url
                    if any(x in u for x in [
                        "/lcnt_tbmt_ttc_ldt",
                        "notify-contractor/find-by-id",
                        "notify-contractor/find-by-notify-no",
                    ]):
                        sniffed["info_json"] = response.json()
                except:
                    pass

            page.on("response", on_response)

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(random.randint(3000, 5000))

                # BƯỚC 1 — Parse dữ liệu từ API
                info_json = sniffed.get("info_json")
                if not info_json:
                    raise Exception("Không bắt được dữ liệu API từ trang này")

                tbmt_data = self.build_tbmt_data(info_json, page.url)
                if not tbmt_data:
                    raise Exception("Không parse được Mã TBMT từ JSON")

                ma_tbmt = tbmt_data["ma_tbmt"]
                logger.info(f"-> Parse OK: Mã TBMT = {ma_tbmt}")

                # Scrape chi phí nộp từ DOM (API không trả về)
                chi_phi_dom = self._scrape_chi_phi_from_page(page)
                if chi_phi_dom > 0:
                    tbmt_data["chi_phi_nop"] = chi_phi_dom
                    logger.info(f"-> Scrape chi phí nộp từ DOM: {chi_phi_dom:,.0f} VND")
                else:
                    logger.warning("-> Không scrape được chi phí nộp từ DOM, giữ giá trị từ API")

                # BƯỚC 2 — Lưu DB
                hsmt_id = self.save_package_to_db(tbmt_data)
                if not hsmt_id:
                    raise Exception("Lỗi lưu Database")
                logger.info(f"-> Lưu DB OK: HSMT_ID = {hsmt_id}")

                # BƯỚC 3 — Tải Webform & Upload MinIO
                try:
                    page.locator("text='Hồ sơ mời thầu'").first.click(timeout=10000)
                    page.wait_for_timeout(2000)

                    webform_btn = page.locator("text='Tải tất cả biểu mẫu webform'").first
                    if not webform_btn.is_visible(timeout=5000):
                        logger.warning("-> Không thấy nút 'Tải tất cả biểu mẫu webform'")
                    else:
                        logger.info("-> Đang tải E-HSMT webform...")
                        with context.expect_page(timeout=20000) as new_page_info:
                            webform_btn.click()

                        viewer = new_page_info.value
                        viewer.wait_for_load_state("domcontentloaded")

                        dl_btn = viewer.locator("button.btn-primary:has-text('Tải về')").first
                        dl_btn.wait_for(state="visible", timeout=15000)
                        viewer.wait_for_timeout(2000)

                        with viewer.expect_download(timeout=90000) as dl_info:
                            try:
                                dl_btn.click(force=True, timeout=5000)
                            except:
                                viewer.evaluate("document.querySelector('button.btn-primary').click()")

                        download = dl_info.value
                        filename     = download.suggested_filename
                        safe_name    = self._sanitize(filename)
                        safe_ma_tbmt = ma_tbmt.replace('/', '_').replace(' ', '').strip()
                        object_name  = f"{safe_ma_tbmt}/{safe_name}"
                        tmp_path     = os.path.join(self.download_dir, safe_name)

                        download.save_as(tmp_path)
                        mime_type, _ = mimetypes.guess_type(tmp_path)
                        mime_type = mime_type or "application/octet-stream"

                        minio_url = self.minio.upload_file(tmp_path, object_name, mime_type)
                        if minio_url:
                            logger.info(f"-> Upload MinIO OK: {minio_url}")
                            self.update_file_path(ma_tbmt, minio_url, filename)
                        else:
                            logger.error("-> Upload MinIO thất bại")

                        try:
                            os.remove(tmp_path)
                        except:
                            pass
                        viewer.close()

                except Exception as e:
                    logger.error(f"-> Lỗi tải file: {e}")

            except Exception as e:
                logger.error(f"Chi tiết lỗi process_package: {e}")
                raise
            finally:
                context.close()
                browser.close()

    # ---------------------------------------------------------
    # TÌM KIẾM THEO RULE
    # ---------------------------------------------------------
    def execute_rule_search(self, rule: CrawlRule):
        logger.info(f">>> BẮT ĐẦU CHẠY RULE: {rule.rule_name}")
        log_id = self.create_crawl_log(rule.id)
        list_packages: list[str] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(user_agent=random.choice(USER_AGENTS))
            page = context.new_page()

            try:
                page.goto(
                    "https://muasamcong.mpi.gov.vn/web/guest/contractor-selection?render=index",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                page.wait_for_timeout(5000)

                # Mở form tìm kiếm nâng cao
                try:
                    page.locator("text='Tìm kiếm nâng cao'").first.click(timeout=5000)
                    page.wait_for_timeout(2000)
                except:
                    logger.warning("-> Không tìm thấy nút 'Tìm kiếm nâng cao' hoặc đã mở sẵn.")

                # Từ khóa
                if rule.keywords_include and isinstance(rule.keywords_include, list) and rule.keywords_include:
                    kw = rule.keywords_include[0]
                    page.locator("input[placeholder*='TBMT'], input[placeholder*='Tên gói thầu']").first.fill(kw)
                    logger.info(f"-> Điền từ khóa: {kw}")

                # Từ khóa loại trừ
                if rule.keywords_exclude and isinstance(rule.keywords_exclude, list) and rule.keywords_exclude:
                    exclude_str = ", ".join(rule.keywords_exclude)
                    try:
                        excl_inp = page.locator("text='Không chứa từ'").locator("..").locator("input").first
                        excl_inp.fill(exclude_str)
                        logger.info(f"-> Điền từ khóa loại trừ: {exclude_str}")
                    except Exception as e:
                        logger.warning(f"-> Lỗi điền từ khóa loại trừ: {e}")

                # Lĩnh vực
                if rule.business_field:
                    try:
                        page.locator(f"label:has-text('{rule.business_field.strip()}')").first.click()
                        page.wait_for_timeout(3000)
                        logger.info(f"-> Chọn lĩnh vực: {rule.business_field}")
                    except Exception as e:
                        logger.warning(f"-> Lỗi chọn lĩnh vực: {e}")

                # Giá gói thầu
                if rule.min_budget or rule.max_budget:
                    try:
                        if rule.min_budget:
                            page.locator("input[placeholder='Từ']").fill(str(int(rule.min_budget)))
                        if rule.max_budget:
                            page.locator("input[placeholder='Đến']").fill(str(int(rule.max_budget)))
                    except Exception as e:
                        logger.warning(f"-> Lỗi điền giá: {e}")

                # Click tìm kiếm
                page.locator("button:has-text('Tìm kiếm')").last.click()
                logger.info("-> Đã click Tìm kiếm!")
                page.wait_for_timeout(5000)

                # Chọn 50 kết quả/trang
                try:
                    page.locator("select").last.select_option("50")
                    page.wait_for_timeout(5000)
                except:
                    pass

                # Scroll để load hết
                page.evaluate("""
                    let h = 0;
                    let t = setInterval(() => {
                        window.scrollBy(0, 500); h += 500;
                        if (h >= document.body.scrollHeight) clearInterval(t);
                    }, 400);
                """)
                page.wait_for_timeout(8000)

                # Thu thập links
                seen: set[str] = set()
                cards = page.locator("div.content__body__left__item__infor").all()
                for card in cards:
                    link_el = card.locator("a[href*='stepCode=notify']").first
                    if link_el.is_visible():
                        href = link_el.get_attribute("href")
                        if href:
                            full_url = href if href.startswith("http") else f"https://muasamcong.mpi.gov.vn{href}"
                            if full_url not in seen:
                                seen.add(full_url)
                                list_packages.append(full_url)
                    if len(list_packages) >= 50:
                        break

                logger.info(f"-> Tìm thấy {len(list_packages)} gói thầu.")

            except Exception as e:
                logger.error(f"Lỗi fatal trong execute_rule_search: {e}")
                self.update_crawl_log(log_id, "CRASHED", error=str(e))
            finally:
                context.close()
                browser.close()

        # Crawl từng gói
        success_count = 0
        fail_count    = 0
        fail_details: list[dict] = []

        for idx, pkg_url in enumerate(list_packages):
            logger.info(f"=== PROCESSING {idx + 1}/{len(list_packages)}: {pkg_url} ===")
            try:
                self.process_package(pkg_url)
                success_count += 1
            except Exception as e:
                fail_count += 1
                fail_details.append({"url": pkg_url, "error": str(e)})
                logger.error(f"Lỗi gói {pkg_url}: {e}")

        final_status = "SUCCESS"
        if fail_count > 0:
            final_status = "WARNING" if success_count > 0 else "FAILED"

        self.update_crawl_log(
            log_id, status=final_status,
            count=success_count, failed=fail_count, details=fail_details,
        )


# ==============================================================================
# SCHEDULER
# ==============================================================================
global_scheduler = None


def load_jobs_from_db(scheduler):
    try:
        scheduler.remove_all_jobs()
        logger.info("-> [Reload] Đã xóa các lịch trình cũ.")
        with SessionLocal() as db:
            schedules = db.query(CrawlSchedule).filter(CrawlSchedule.is_active == True).all()
            logger.info(f"-> [Reload] Tìm thấy {len(schedules)} lịch active.")
            for sched in schedules:
                def job_wrapper(s_id=sched.id):
                    logger.info(f"⏰ [Auto] ĐẾN GIỜ CHẠY SCHEDULE ID: {s_id}")
                    try:
                        bot = MuasamcongDBBot()
                        with SessionLocal() as session:
                            rules = session.query(CrawlRule).filter(CrawlRule.is_active == True).all()
                            logger.info(f"-> Tìm thấy {len(rules)} luật đang kích hoạt.")
                            for rule in rules:
                                bot.execute_rule_search(rule)
                    except Exception as e:
                        logger.error(f"❌ Lỗi Job {s_id}: {e}")

                parts = sched.cron_expression.split()
                if len(parts) == 5:
                    trigger = CronTrigger(
                        minute=parts[0], hour=parts[1], day=parts[2],
                        month=parts[3], day_of_week=parts[4],
                        timezone="Asia/Ho_Chi_Minh",
                    )
                    scheduler.add_job(job_wrapper, trigger, id=f"sched_{sched.id}", replace_existing=True)
                    logger.info(f"   + Đã nạp lịch ID {sched.id}: {sched.cron_expression}")

        print("\n--- LỊCH TRÌNH ĐÃ CẬP NHẬT ---")
        scheduler.print_jobs()
        print("------------------------------\n")
    except Exception as e:
        logger.error(f"Lỗi khi nạp lại Job: {e}")


def start_scheduler_service():
    global global_scheduler
    if global_scheduler is None:
        global_scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
        global_scheduler.start()
        logger.info(">>> SCHEDULER STARTED <<<")
    load_jobs_from_db(global_scheduler)
    return global_scheduler


def reload_scheduler():
    global global_scheduler
    if global_scheduler and global_scheduler.running:
        load_jobs_from_db(global_scheduler)
        return True
    return False


def run_scheduler_system():
    scheduler = start_scheduler_service()
    if scheduler:
        try:
            while True:
                time.sleep(2)
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()


if __name__ == "__main__":
    print("!!! ĐANG CHẠY CHẾ ĐỘ THỦ CÔNG (TEST LINK LẺ) !!!")
    target_url = "https://muasamcong.mpi.gov.vn/web/guest/contractor-selection?p_p_id=egpportalcontractorselectionv2_WAR_egpportalcontractorselectionv2&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view&_egpportalcontractorselectionv2_WAR_egpportalcontractorselectionv2_render=detail-v2&type=es-notify-contractor&stepCode=notify-contractor-step-1-tbmt&id=2f6b1b5c-cb70-498d-ab23-4bd5bdc3303b&notifyId=2f6b1b5c-cb70-498d-ab23-4bd5bdc3303b&inputResultId=undefined&bidOpenId=undefined&techReqId=undefined&bidPreNotifyResultId=undefined&bidPreOpenId=undefined&processApply=LDT&bidMode=1_MTHS&notifyNo=IB2600200306&planNo=PL2600108819&pno=undefined&step=tbmt&isInternet=1&caseKHKQ=undefined&bidForm=CHCT"

    print(f"BẮT ĐẦU CHẠY CHO LINK:\n{target_url}")
    try:
        bot = MuasamcongDBBot()
        bot.process_package(target_url)
        print("ĐÃ CHẠY XONG!")
    except Exception as e:
        print(f"CÓ LỖI XẢY RA: {e}")
        import traceback
        traceback.print_exc()
