"""
RabbitMQ queue configuration and message schemas
"""
from typing import Dict, Any, Optional, List
from enum import Enum
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID


class QueueName(str, Enum):
    """Queue names for different types of tasks"""
    ASSET_PROCESSING = "asset_processing"
    GENERATION = "generation"
    MODERATION = "moderation"
    PRIORITY = "priority"
    DLQ = "dead_letter_queue"  # Dead Letter Queue


class TaskPriority(int, Enum):
    """Task priority levels"""
    LOW = 1
    NORMAL = 5
    HIGH = 8
    CRITICAL = 10


class MessageType(str, Enum):
    """Types of messages that can be sent"""
    ASSET_UPLOAD = "asset_upload"
    ASSET_ANALYSIS = "asset_analysis"
    GENERATION_REQUEST = "generation_request"
    CONTENT_MODERATION = "content_moderation"
    MANUAL_EDIT = "manual_edit"
    BATCH_PROCESSING = "batch_processing"


# Base message schema
class BaseMessage(BaseModel):
    """Base message schema for all queue messages"""
    message_id: str
    message_type: MessageType
    user_id: UUID
    created_at: datetime
    priority: TaskPriority = TaskPriority.NORMAL
    retry_count: int = 0
    max_retries: int = 3
    metadata: Dict[str, Any] = {}


# Asset processing messages
class AssetUploadMessage(BaseMessage):
    """Message for asset upload processing"""
    message_type: MessageType = MessageType.ASSET_UPLOAD
    asset_id: UUID
    project_id: UUID
    user_id: UUID
    file_path: str
    original_filename: str
    file_size: int
    mime_type: str
    ai_provider: Optional[str] = None  # Preferred AI provider for analysis


class AssetAnalysisMessage(BaseMessage):
    """Message for AI asset analysis"""
    message_type: MessageType = MessageType.ASSET_ANALYSIS
    asset_id: UUID
    file_path: str
    analysis_type: str = "full"  # full, elements_only, moderation_only
    ai_provider: Optional[str] = None


# Generation messages
class GenerationRequestMessage(BaseMessage):
    """Message for asset generation requests"""
    message_type: MessageType = MessageType.GENERATION_REQUEST
    job_id: UUID
    project_id: UUID
    asset_ids: List[UUID]
    format_ids: List[UUID]
    custom_sizes: List[Dict[str, int]] = []
    generation_settings: Dict[str, Any] = {}
    provider: Optional[str] = None


class ManualEditMessage(BaseMessage):
    """Message for manual edit application"""
    message_type: MessageType = MessageType.MANUAL_EDIT
    asset_id: UUID
    generated_asset_id: UUID
    edit_operations: Dict[str, Any]
    output_format: str = "jpeg"
    quality: str = "high"


# Moderation messages
class ContentModerationMessage(BaseMessage):
    """Message for content moderation"""
    message_type: MessageType = MessageType.CONTENT_MODERATION
    asset_id: UUID
    file_path: str
    moderation_rules: Dict[str, Any]
    ai_provider: Optional[str] = None


class BatchProcessingMessage(BaseMessage):
    """Message for batch processing operations"""
    message_type: MessageType = MessageType.BATCH_PROCESSING
    batch_id: UUID
    operation_type: str  # analysis, generation, moderation
    asset_ids: List[UUID]
    batch_settings: Dict[str, Any] = {}


# Queue configuration
QUEUE_CONFIG = {
    QueueName.ASSET_PROCESSING: {
        "durable": True,
        "auto_delete": False,
        "arguments": {
            "x-message-ttl": 3600000,  # 1 hour TTL
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": QueueName.DLQ,
        }
    },
    QueueName.GENERATION: {
        "durable": True,
        "auto_delete": False,
        "arguments": {
            "x-message-ttl": 7200000,  # 2 hours TTL
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": QueueName.DLQ,
        }
    },
    QueueName.MODERATION: {
        "durable": True,
        "auto_delete": False,
        "arguments": {
            "x-message-ttl": 1800000,  # 30 minutes TTL
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": QueueName.DLQ,
        }
    },
    QueueName.PRIORITY: {
        "durable": True,
        "auto_delete": False,
        "arguments": {
            "x-max-priority": 10,
            "x-message-ttl": 600000,  # 10 minutes TTL
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": QueueName.DLQ,
        }
    },
    QueueName.DLQ: {
        "durable": True,
        "auto_delete": False,
        "arguments": {
            "x-message-ttl": 86400000,  # 24 hours TTL
        }
    }
}

# Exchange configuration
EXCHANGE_CONFIG = {
    "main": {
        "type": "direct",
        "durable": True,
        "auto_delete": False,
    },
    "dlx": {  # Dead Letter Exchange
        "type": "direct",
        "durable": True,
        "auto_delete": False,
    }
}

# Routing keys
ROUTING_KEYS = {
    MessageType.ASSET_UPLOAD: QueueName.ASSET_PROCESSING,
    MessageType.ASSET_ANALYSIS: QueueName.ASSET_PROCESSING,
    MessageType.GENERATION_REQUEST: QueueName.GENERATION,
    MessageType.CONTENT_MODERATION: QueueName.MODERATION,
    MessageType.MANUAL_EDIT: QueueName.GENERATION,
    MessageType.BATCH_PROCESSING: QueueName.ASSET_PROCESSING,
}


class QueueManager:
    """Manager for queue operations and monitoring"""
    
    def __init__(self, celery_app):
        self.celery_app = celery_app
        self.connection = None
    
    def setup_queues(self):
        """Set up all queues, exchanges, and bindings"""
        try:
            # This would be called during application startup
            # to ensure all queues and exchanges exist
            pass
        except Exception as e:
            print(f"Error setting up queues: {e}")
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """Get statistics for all queues"""
        try:
            inspect = self.celery_app.control.inspect()
            active_queues = inspect.active_queues()
            reserved_tasks = inspect.reserved()
            
            stats = {
                "active_queues": active_queues,
                "reserved_tasks": reserved_tasks,
                "queue_lengths": self._get_queue_lengths(),
            }
            
            return stats
        except Exception as e:
            return {"error": str(e)}
    
    def _get_queue_lengths(self) -> Dict[str, int]:
        """Get the length of each queue"""
        # This would require direct RabbitMQ connection
        # For now, return placeholder data
        return {
            queue.value: 0 for queue in QueueName
        }
    
    def purge_queue(self, queue_name: QueueName) -> bool:
        """Purge all messages from a queue"""
        try:
            self.celery_app.control.purge()
            return True
        except Exception as e:
            print(f"Error purging queue {queue_name}: {e}")
            return False
    
    def get_failed_tasks(self) -> List[Dict[str, Any]]:
        """Get failed tasks from dead letter queue"""
        # This would require direct RabbitMQ connection
        # For now, return placeholder data
        return []


# Message factory functions
def create_asset_upload_message(
    user_id: UUID,
    asset_id: UUID,
    project_id: UUID,
    file_path: str,
    original_filename: str,
    file_size: int,
    mime_type: str,
    priority: TaskPriority = TaskPriority.NORMAL,
    ai_provider: Optional[str] = None
) -> AssetUploadMessage:
    """Create an asset upload message"""
    import uuid
    from datetime import datetime
    
    return AssetUploadMessage(
        message_id=str(uuid.uuid4()),
        user_id=user_id,
        asset_id=asset_id,
        project_id=project_id,
        file_path=file_path,
        original_filename=original_filename,
        file_size=file_size,
        mime_type=mime_type,
        priority=priority,
        ai_provider=ai_provider,
        created_at=datetime.utcnow()
    )


def create_generation_request_message(
    user_id: UUID,
    job_id: UUID,
    project_id: UUID,
    asset_ids: List[UUID],
    format_ids: List[UUID],
    custom_sizes: List[Dict[str, int]] = None,
    priority: TaskPriority = TaskPriority.NORMAL,
    provider: Optional[str] = None
) -> GenerationRequestMessage:
    """Create a generation request message"""
    import uuid
    from datetime import datetime
    
    return GenerationRequestMessage(
        message_id=str(uuid.uuid4()),
        user_id=user_id,
        job_id=job_id,
        project_id=project_id,
        asset_ids=asset_ids,
        format_ids=format_ids,
        custom_sizes=custom_sizes or [],
        priority=priority,
        provider=provider,
        created_at=datetime.utcnow()
    )


def create_moderation_message(
    user_id: UUID,
    asset_id: UUID,
    file_path: str,
    moderation_rules: Dict[str, Any],
    priority: TaskPriority = TaskPriority.HIGH
) -> ContentModerationMessage:
    """Create a content moderation message"""
    import uuid
    from datetime import datetime
    
    return ContentModerationMessage(
        message_id=str(uuid.uuid4()),
        user_id=user_id,
        asset_id=asset_id,
        file_path=file_path,
        moderation_rules=moderation_rules,
        priority=priority,
        created_at=datetime.utcnow()
    )