"""
AI Provider specific exceptions
"""


class AIProviderError(Exception):
    """Base exception for AI provider errors"""
    pass


class RateLimitError(AIProviderError):
    """Raised when API rate limit is exceeded"""
    def __init__(self, message: str, retry_after: int = None):
        super().__init__(message)
        self.retry_after = retry_after


class InvalidImageError(AIProviderError):
    """Raised when image format or content is invalid"""
    pass


class AuthenticationError(AIProviderError):
    """Raised when API authentication fails"""
    pass


class QuotaExceededError(AIProviderError):
    """Raised when API quota is exceeded"""
    pass


class ServiceUnavailableError(AIProviderError):
    """Raised when AI service is temporarily unavailable"""
    pass