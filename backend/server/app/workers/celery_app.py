"""
Celery application configuration with RabbitMQ queue management
"""
from celery import Celery
from kombu import Queue, Exchange
from app.core.config import settings
from app.workers.queue_config import QueueName, QUEUE_CONFIG, EXCHANGE_CONFIG

# Create Celery app with optional broker connection
try:
    celery_app = Celery(
        "ai_creat_worker",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
        include=[
            "app.workers.asset_processing",
            "app.workers.generation",
            "app.workers.moderation",
        ]
    )
except Exception as e:
    # Create Celery app without broker for development/testing
    celery_app = Celery(
        "ai_creat_worker",
        broker="memory://",
        backend="rpc://",
        include=[
            "app.workers.asset_processing",
            "app.workers.generation",
            "app.workers.moderation",
        ]
    )

# Define exchanges
main_exchange = Exchange("main", type="direct", durable=True)
dlx_exchange = Exchange("dlx", type="direct", durable=True)

# Define queues with proper configuration
task_queues = [
    Queue(
        QueueName.ASSET_PROCESSING,
        main_exchange,
        routing_key=QueueName.ASSET_PROCESSING,
        queue_arguments=QUEUE_CONFIG[QueueName.ASSET_PROCESSING]["arguments"]
    ),
    Queue(
        QueueName.GENERATION,
        main_exchange,
        routing_key=QueueName.GENERATION,
        queue_arguments=QUEUE_CONFIG[QueueName.GENERATION]["arguments"]
    ),
    Queue(
        QueueName.MODERATION,
        main_exchange,
        routing_key=QueueName.MODERATION,
        queue_arguments=QUEUE_CONFIG[QueueName.MODERATION]["arguments"]
    ),
    Queue(
        QueueName.PRIORITY,
        main_exchange,
        routing_key=QueueName.PRIORITY,
        queue_arguments=QUEUE_CONFIG[QueueName.PRIORITY]["arguments"]
    ),
    Queue(
        QueueName.DLQ,
        dlx_exchange,
        routing_key=QueueName.DLQ,
        queue_arguments=QUEUE_CONFIG[QueueName.DLQ]["arguments"]
    ),
]

# Configure Celery
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # Timezone
    timezone="UTC",
    enable_utc=True,
    
    # Task execution
    task_track_started=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    
    # Retry configuration
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,
    
    # Queue configuration
    task_queues=task_queues,
    task_default_queue=QueueName.ASSET_PROCESSING,
    task_default_exchange="main",
    task_default_exchange_type="direct",
    task_default_routing_key=QueueName.ASSET_PROCESSING,
    
    # Task routing
    task_routes={
        "app.workers.asset_processing.analyze_asset": {
            "queue": QueueName.ASSET_PROCESSING,
            "routing_key": QueueName.ASSET_PROCESSING
        },
        "app.workers.asset_processing.process_upload": {
            "queue": QueueName.ASSET_PROCESSING,
            "routing_key": QueueName.ASSET_PROCESSING
        },
        "app.workers.generation.generate_assets": {
            "queue": QueueName.GENERATION,
            "routing_key": QueueName.GENERATION
        },
        "app.workers.generation.apply_manual_edits": {
            "queue": QueueName.GENERATION,
            "routing_key": QueueName.GENERATION
        },
        "app.workers.moderation.moderate_content": {
            "queue": QueueName.MODERATION,
            "routing_key": QueueName.MODERATION
        },
        # Priority tasks
        "app.workers.*.priority_*": {
            "queue": QueueName.PRIORITY,
            "routing_key": QueueName.PRIORITY
        },
    },
    
    # Result backend configuration
    result_expires=3600,  # 1 hour
    result_persistent=True,
    
    # Worker configuration
    worker_send_task_events=True,
    task_send_sent_event=True,
    
    # Monitoring
    worker_hijack_root_logger=False,
    worker_log_format="[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
    worker_task_log_format="[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s",
)

# Initialize queue manager
from app.workers.queue_config import QueueManager
queue_manager = QueueManager(celery_app)