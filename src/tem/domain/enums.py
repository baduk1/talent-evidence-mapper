from enum import Enum

class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class TaskStatus(str, Enum):
    CREATED = "created"
    VALIDATING = "validating"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"


class TransactionType(str, Enum):
    CREDIT = "credit"
    DEBIT = "debit"


class EvidenceCategory(str, Enum):
    INNOVATION = "innovation"
    RECOGNITION_LEADER = "recognition_leader"
    RECOGNITION_POTENTIAL = "recognition_potential"
    SIGNIFICANT_CONTRIBUTION = "significant_contribution"
    ACADEMIC_CONTRIBUTION = "academic_contribution"
    OUTSIDE_WORK = "outside_work"
    IRRELEVANT = "irrelevant"
    INSUFFICIENT = "insufficiaent"
    