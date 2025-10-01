"""
Enums for the AI CREAT platform
"""
import enum


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class ProjectStatus(str, enum.Enum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY_FOR_REVIEW = "ready_for_review"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PlatformType(str, enum.Enum):
    RESIZING = "resizing"
    REPURPOSING = "repurposing"


class AssetStatus(str, enum.Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"
    READY_FOR_GENERATION = "ready_for_generation"