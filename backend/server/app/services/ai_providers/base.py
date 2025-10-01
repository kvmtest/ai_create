"""
Base AI Provider interface and data models
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
from .exceptions import InvalidImageError


class ElementType(str, Enum):
    """Types of elements that can be detected in images"""
    FACE = "face"
    PRODUCT = "product"
    TEXT = "text"
    LOGO = "logo"
    OBJECT = "object"
    PERSON = "person"
    BACKGROUND = "background"


class ModerationCategory(str, Enum):
    """Content moderation categories"""
    SAFE = "safe"
    NSFW = "nsfw"
    VIOLENCE = "violence"
    HATE = "hate"
    HARASSMENT = "harassment"
    SELF_HARM = "self_harm"


@dataclass
class DetectedElement:
    """Represents an element detected in an image"""
    type: ElementType
    confidence: float
    bounding_box: Dict[str, float]  # {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}
    description: str
    attributes: Dict[str, Any] = None


@dataclass
class ModerationResult:
    """Result of content moderation analysis"""
    category: ModerationCategory
    confidence: float
    flagged: bool
    categories: Dict[str, float]  # Category scores
    reason: Optional[str] = None


@dataclass
class ImageAnalysis:
    """Complete analysis result for an image"""
    detected_elements: List[DetectedElement]
    moderation: ModerationResult
    metadata: Dict[str, Any]
    processing_time: float
    provider: str


@dataclass
class AdaptationStrategy:
    """Strategy for adapting images to different formats"""
    target_width: int
    target_height: int
    crop_strategy: str = "smart"  # smart, center, top, bottom
    quality: str = "high"  # high, medium, low
    format: str = "jpeg"  # jpeg, png, webp
    background_color: Optional[str] = None


class AIProvider(ABC):
    """Abstract base class for AI providers"""
    
    def __init__(self, api_key: str, **kwargs):
        self.api_key = api_key
        self.config = kwargs
    
    @abstractmethod
    async def analyze_image(self, image_path: str) -> ImageAnalysis:
        """
        Analyze an image and return comprehensive analysis results
        
        Args:
            image_path: Path to the image file
            
        Returns:
            ImageAnalysis object with detected elements and metadata
            
        Raises:
            AIProviderError: If analysis fails
            InvalidImageError: If image is invalid
            RateLimitError: If rate limit is exceeded
        """
        pass
    
    @abstractmethod
    async def detect_elements(self, image_path: str) -> List[DetectedElement]:
        """
        Detect elements in an image
        
        Args:
            image_path: Path to the image file
            
        Returns:
            List of detected elements
        """
        pass
    
    @abstractmethod
    async def moderate_content(self, image_path: str) -> ModerationResult:
        """
        Moderate image content for safety
        
        Args:
            image_path: Path to the image file
            
        Returns:
            ModerationResult with safety assessment
        """
        pass
    
    @abstractmethod
    async def apply_adaptation(self, image_path: str, strategy: AdaptationStrategy) -> str:
        """
        Apply adaptation strategy to resize/crop image
        
        Args:
            image_path: Path to the source image
            strategy: Adaptation strategy to apply
            
        Returns:
            Path to the adapted image file
        """
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of this provider"""
        pass
    
    @property
    @abstractmethod
    def supported_formats(self) -> List[str]:
        """Return list of supported image formats"""
        pass
    
    def validate_image(self, image_path: str) -> bool:
        """
        Validate if image format is supported
        
        Args:
            image_path: Path to the image file
            
        Returns:
            True if image is valid and supported
            
        Raises:
            InvalidImageError: If image is invalid
        """
        import os
        from pathlib import Path
        
        if not os.path.exists(image_path):
            raise InvalidImageError(f"Image file not found: {image_path}")
        
        file_extension = Path(image_path).suffix.lower().lstrip('.')
        if file_extension not in self.supported_formats:
            raise InvalidImageError(
                f"Unsupported image format: {file_extension}. "
                f"Supported formats: {', '.join(self.supported_formats)}"
            )
        
        return True