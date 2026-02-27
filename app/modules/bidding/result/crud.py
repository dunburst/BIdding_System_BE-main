from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import select
from app.modules.bidding.result.model import BiddingResult, BiddingResultWinner
from app.modules.bidding.package.model import BiddingPackage
from app.modules.bidding.result.schema import BiddingResultSummaryResponse, BiddingResultFullResponse
from fastapi import HTTPException

# --- HÀM 1: LẤY KẾT QUẢ TÓM TẮT ---
def get_result_summary(db: Session, hsmt_id: int):
    # 1. Query Result và join với bảng Winner để lấy thông tin
    query = select(BiddingResult).where(BiddingResult.hsmt_id == hsmt_id).options(
        selectinload(BiddingResult.winners)
    )
    result = db.execute(query).unique().scalar_one_or_none()

    if not result:
        return None # Hoặc raise HTTPException tùy logic của bạn

    # 2. Xử lý logic ghép tên và giá
    # Nếu có nhiều người trúng thầu (liên danh), ta cần xử lý khéo léo
    winner_name_display = "Chưa cập nhật"
    winning_price_display = None

    if result.winners:
        # Ưu tiên lấy tên Liên danh (role) nếu có, nếu không thì lấy tên nhà thầu đầu tiên
        # Hoặc ghép chuỗi tên các nhà thầu
        first_winner = result.winners[0]
        
        if first_winner.role: # Nếu có tên liên danh lưu ở cột role
            winner_name_display = first_winner.role
        else:
            # Ghép tên các nhà thầu: "Cty A; Cty B"
            names = [w.bidder_name for w in result.winners if w.bidder_name]
            winner_name_display = "; ".join(names) if names else "N/A"
            
        # Giá trúng thầu: Thường lấy giá của dòng đầu tiên (vì liên danh giá giống nhau)
        # hoặc tổng (tùy dữ liệu nguồn). Ở đây lấy giá của record đầu.
        winning_price_display = first_winner.winning_price

    # 3. Map sang Schema
    return BiddingResultSummaryResponse(
        hsmt_id=result.hsmt_id,
        bidding_result_text=result.bidding_result_text,
        approval_date=result.approval_date,
        winner_name=winner_name_display,
        winning_price=winning_price_display
    )

# --- HÀM 2: LẤY KẾT QUẢ FULL ---
def get_result_full_detail(db: Session, hsmt_id: int):
    # Dùng selectinload để load toàn bộ quan hệ con (Failed, Winner, Items)
    query = select(BiddingResult).where(BiddingResult.hsmt_id == hsmt_id).options(
        selectinload(BiddingResult.winners),
        selectinload(BiddingResult.failed_bidders),
        selectinload(BiddingResult.items)
    )
    
    result = db.execute(query).unique().scalar_one_or_none()
    
    if not result:
        raise HTTPException(status_code=404, detail="Chưa có kết quả đấu thầu cho gói này.")
        
    return result