"""
AI Provider abstraction layer for image analysis and processing
"""
from .base import AIProvider, ImageAnalysis, DetectedElement, ModerationResult, AdaptationStrategy
from .factory import AIProviderFactory, RetryHandler, LoadBalancer
from .config import AIProviderConfigManager, config_manager
from .manager import AIProviderManager, ai_manager
from .exceptions import AIProviderError, RateLimitError, InvalidImageError

from .openai_provider import OpenAIProvider
from .gemini_provider import GeminiProvider

# Register providers
AIProviderFactory.register_provider("openai", OpenAIProvider)
AIProviderFactory.register_provider("gemini", GeminiProvider)

__all__ = [
    "AIProvider",
    "ImageAnalysis", 
    "DetectedElement",
    "ModerationResult",
    "AdaptationStrategy",
    "AIProviderFactory",
    "RetryHandler",
    "LoadBalancer",
    "AIProviderConfigManager",
    "config_manager",
    "AIProviderManager",
    "ai_manager",
    "AIProviderError",
    "RateLimitError", 
    "InvalidImageError",
    "OpenAIProvider",
    "GeminiProvider"
]