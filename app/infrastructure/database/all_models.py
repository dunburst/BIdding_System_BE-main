# Import tất cả các model đã tách để Base.metadata nhận diện được
from app.modules.users.model import User
from app.modules.organization.model import OrganizationalUnit, AuditLog
from app.modules.crawler_config.model import CrawlSchedule, CrawlRule, CrawlLog
from app.modules.abac_config.model import AbacAttribute, AbacPolicy
from app.modules.drafting.model import DocumentTemplate, DocumentRegistry

# Import module Bidding (cấu trúc thư mục con)
from app.modules.bidding.project.model import BiddingProject, BidSubmitLog
from app.modules.bidding.package.model import BiddingPackage, BiddingPackageFile
from app.modules.bidding.task.model import (
    BiddingTask, TaskAssignment, TaskComment, TaskHistory,
    BiddingProjectTemplate, BiddingTaskTemplate, TemplateStructure
)
from app.modules.bidding.result.model import (
    BiddingResult, BiddingResultWinner, BiddingResultFailed, BiddingResultItem
)
from app.modules.bidding.requirement.model import (
    BiddingReqFinancialAdmin, BiddingReqPersonnel, BiddingReqEquipment
)