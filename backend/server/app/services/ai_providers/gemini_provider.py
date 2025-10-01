"""
Google Gemini Provider implementation for image analysis and processing
"""
import asyncio
import json
import time
from typing import List, Dict, Any
from pathlib import Path
import aiohttp
from PIL import Image
import io
import base64
import structlog

from .resizer.resizer import resize
from .base import AIProvider, ImageAnalysis, DetectedElement, ModerationResult, AdaptationStrategy
from .base import ElementType, ModerationCategory
from .exceptions import AIProviderError, RateLimitError, AuthenticationError, QuotaExceededError

logger = structlog.get_logger()


class GeminiProvider(AIProvider):
    """Google Gemini provider implementation using Gemini Pro Vision API"""
    
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-image-preview", **kwargs):
        super().__init__(api_key, **kwargs)
        self.model = model
        self.base_url = "https://generativelanguage.googleapis.com/v1"
        self.timeout = kwargs.get('timeout', 60)
        self.max_requests_per_minute = kwargs.get('max_requests_per_minute', 60)
    
    @property
    def provider_name(self) -> str:
        return "gemini"
    
    @property
    def supported_formats(self) -> List[str]:
        return ["jpg", "jpeg", "png", "webp"]
    
    async def analyze_image(self, image_path: str) -> ImageAnalysis:
        """Analyze image using Gemini Pro Vision API"""
        logger.info(
            "Starting Gemini image analysis",
            provider="gemini",
            model=self.model,
            image_path=image_path
        )
        
        self.validate_image(image_path)
        start_time = time.time()
        
        try:
            # Get image analysis and moderation in parallel
            analysis_task = self._analyze_with_vision(image_path)
            moderation_task = self.moderate_content(image_path)
            
            elements, metadata = await analysis_task
            moderation = await moderation_task
            
            processing_time = time.time() - start_time
            
            logger.info(
                "Gemini image analysis completed",
                provider="gemini",
                model=self.model,
                image_path=image_path,
                processing_time=round(processing_time, 2),
                elements_detected=len(elements),
                moderation_flagged=moderation.flagged
            )
            
            return ImageAnalysis(
                detected_elements=elements,
                moderation=moderation,
                metadata=metadata,
                processing_time=processing_time,
                provider=self.provider_name
            )
        except Exception as e:
            logger.error(
                "Gemini image analysis failed",
                provider="gemini",
                model=self.model,
                image_path=image_path,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    async def detect_elements(self, image_path: str) -> List[DetectedElement]:
        """Detect elements using Gemini Vision API"""
        self.validate_image(image_path)
        elements, _ = await self._analyze_with_vision(image_path)
        return elements
    
    async def moderate_content(self, image_path: str) -> ModerationResult:
        """Moderate content using Gemini API"""
        self.validate_image(image_path)
        
        # Prepare image data
        image_data = self._prepare_image_data(image_path)
        
        url = f"{self.base_url}/models/{self.model}:generateContent"
        headers = {
            "Content-Type": "application/json"
        }
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": "Analyze this image for content safety. Classify it into one of these categories: safe, nsfw, violence, hate, harassment, self_harm. Provide confidence scores (0-1) for each category. Respond in JSON format: {\"category\": \"safe\", \"confidence\": 0.95, \"scores\": {\"safe\": 0.95, \"nsfw\": 0.05, \"violence\": 0.0, \"hate\": 0.0, \"harassment\": 0.0, \"self_harm\": 0.0}, \"flagged\": false, \"reason\": \"explanation\"}"
                        },
                        {
                            "inline_data": image_data
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 300
            }
        }
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                async with session.post(f"{url}?key={self.api_key}", headers=headers, json=payload) as response:
                    await self._handle_response_errors(response)
                    result = await response.json()
                    
                    return self._parse_moderation_response(result)
        
        except aiohttp.ClientError as e:
            raise AIProviderError(f"Gemini API request failed: {e}")
    
    async def apply_adaptation(self, image_path: str, strategy: AdaptationStrategy) -> str:
        """Apply adaptation strategy using image processing"""
        self.validate_image(image_path)
        
        # Use PIL for basic image processing (same as OpenAI provider)
        return self._resize_image(image_path, strategy)
    
    async def _analyze_with_vision(self, image_path: str) -> tuple[List[DetectedElement], Dict[str, Any]]:
        """Analyze image using Gemini Pro Vision API"""
        logger.info(
            "Preparing Gemini API request",
            provider="gemini",
            model=self.model,
            image_path=image_path
        )
        
        image_data = self._prepare_image_data(image_path)
        
        url = f"{self.base_url}/models/{self.model}:generateContent"
        headers = {
            "Content-Type": "application/json"
        }
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": """Analyze this image in detail and provide a JSON response with this exact structure:
                            {
                                "elements": [
                                    {
                                        "type": "face|product|text|logo|object|person|background",
                                        "confidence": 0.95,
                                        "bounding_box": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
                                        "description": "detailed description of what you see",
                                        "attributes": {"key": "value pairs with additional details"}
                                    }
                                ],
                                "metadata": {
                                    "dimensions": {"width": 1920, "height": 1080},
                                    "dominant_colors": ["#FF0000", "#00FF00", "#0000FF"],
                                    "style": "modern|vintage|minimalist|abstract|realistic|etc",
                                    "composition": "description of the overall layout and arrangement",
                                    "quality_assessment": "high|medium|low",
                                    "lighting": "bright|dim|natural|artificial|etc",
                                    "mood": "happy|serious|energetic|calm|etc"
                                }
                            }
                            
                            Use normalized coordinates (0-1) for bounding boxes. Be precise and thorough."""
                        },
                        {
                            "inline_data": image_data
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1500
            }
        }
        
        try:
            logger.info("Sending request to Gemini API", provider="gemini", model=self.model)
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                async with session.post(f"{url}?key={self.api_key}", headers=headers, json=payload) as response:
                    logger.info(
                        "Gemini API response received",
                        provider="gemini",
                        status_code=response.status,
                        content_length=response.headers.get('Content-Length', 'unknown')
                    )
                    
                    await self._handle_response_errors(response)
                    result = await response.json()
                    
                    elements, metadata = self._parse_vision_response(result)
                    logger.info(
                        "Gemini API response parsed successfully",
                        provider="gemini",
                        elements_found=len(elements),
                        has_metadata=bool(metadata)
                    )
                    
                    return elements, metadata
        
        except aiohttp.ClientError as e:
            logger.error(
                "Gemini API request failed",
                provider="gemini",
                error=str(e),
                error_type=type(e).__name__
            )
            raise AIProviderError(f"Gemini API request failed: {e}")
        except Exception as e:
            logger.error(
                "Unexpected error in Gemini API call",
                provider="gemini",
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    def _prepare_image_data(self, image_path: str) -> Dict[str, str]:
        """Prepare image data for Gemini API"""
        try:
            with open(image_path, "rb") as image_file:
                image_bytes = image_file.read()
                image_b64 = base64.b64encode(image_bytes).decode('utf-8')
                
                # Determine MIME type
                file_extension = Path(image_path).suffix.lower()
                mime_type_map = {
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.png': 'image/png',
                    '.webp': 'image/webp'
                }
                mime_type = mime_type_map.get(file_extension, 'image/jpeg')
                
                return {
                    "mime_type": mime_type,
                    "data": image_b64
                }
        except Exception as e:
            raise AIProviderError(f"Failed to prepare image data: {e}")
    
    async def _handle_response_errors(self, response: aiohttp.ClientResponse):
        """Handle Gemini API response errors"""
        if response.status == 200:
            return
        
        try:
            error_data = await response.json()
            error_message = error_data.get('error', {}).get('message', 'Unknown error')
        except:
            error_message = f"HTTP {response.status}"
        
        # Log the error with appropriate level
        if response.status == 401 or response.status == 403:
            logger.error(
                "Gemini authentication failed",
                provider="gemini",
                status_code=response.status,
                error_message=error_message
            )
            raise AuthenticationError(f"Gemini authentication failed: {error_message}")
        elif response.status == 429:
            # Extract retry-after header if available
            retry_after = response.headers.get('retry-after')
            retry_after = int(retry_after) if retry_after else None
            logger.warning(
                "Gemini rate limit exceeded",
                provider="gemini",
                retry_after_seconds=retry_after,
                error_message=error_message
            )
            raise RateLimitError(f"Gemini rate limit exceeded: {error_message}", retry_after)
        elif response.status == 402:
            logger.error(
                "Gemini quota exceeded",
                provider="gemini",
                error_message=error_message
            )
            raise QuotaExceededError(f"Gemini quota exceeded: {error_message}")
        else:
            logger.error(
                "Gemini API error",
                provider="gemini",
                status_code=response.status,
                error_message=error_message
            )
            raise AIProviderError(f"Gemini API error {response.status}: {error_message}")
    
    def _parse_vision_response(self, response: Dict) -> tuple[List[DetectedElement], Dict[str, Any]]:
        """Parse Gemini Vision API response"""
        try:
            # Extract text content from Gemini response
            candidates = response.get('candidates', [])
            if not candidates:
                return self._create_fallback_elements(), self._create_fallback_metadata()
            
            content = candidates[0].get('content', {})
            parts = content.get('parts', [])
            if not parts:
                return self._create_fallback_elements(), self._create_fallback_metadata()
            
            text_content = parts[0].get('text', '')
            
            # Try to extract JSON from the response
            json_start = text_content.find('{')
            json_end = text_content.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = text_content[json_start:json_end]
                data = json.loads(json_str)
            else:
                # Fallback: create analysis based on text content
                data = self._create_fallback_analysis(text_content)
            
            elements = []
            for elem_data in data.get('elements', []):
                element_type = self._map_element_type(elem_data.get('type', 'object'))
                elements.append(DetectedElement(
                    type=element_type,
                    confidence=elem_data.get('confidence', 0.8),
                    bounding_box=elem_data.get('bounding_box', {"x": 0, "y": 0, "width": 1, "height": 1}),
                    description=elem_data.get('description', ''),
                    attributes=elem_data.get('attributes', {})
                ))
            
            metadata = data.get('metadata', {})
            
            return elements, metadata
        
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            # Fallback to basic analysis
            return self._create_fallback_elements(), self._create_fallback_metadata()
    
    def _parse_moderation_response(self, response: Dict) -> ModerationResult:
        """Parse moderation response from Gemini"""
        try:
            # Extract text content from Gemini response
            candidates = response.get('candidates', [])
            if not candidates:
                return self._create_fallback_moderation()
            
            content = candidates[0].get('content', {})
            parts = content.get('parts', [])
            if not parts:
                return self._create_fallback_moderation()
            
            text_content = parts[0].get('text', '')
            
            # Try to extract JSON from the response
            json_start = text_content.find('{')
            json_end = text_content.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = text_content[json_start:json_end]
                data = json.loads(json_str)
                
                category = data.get('category', 'safe')
                confidence = data.get('confidence', 0.9)
                scores = data.get('scores', {})
                flagged = data.get('flagged', False)
                
                # Ensure all required categories are present
                default_scores = {
                    "safe": 0.9,
                    "nsfw": 0.1,
                    "violence": 0.0,
                    "hate": 0.0,
                    "harassment": 0.0,
                    "self_harm": 0.0
                }
                default_scores.update(scores)
                
                return ModerationResult(
                    category=ModerationCategory(category),
                    confidence=confidence,
                    flagged=flagged,
                    categories=default_scores,
                    reason=data.get('reason')
                )
            else:
                # Fallback based on text analysis
                return self._analyze_text_for_moderation(text_content)
        
        except Exception:
            return self._create_fallback_moderation()
    
    def _map_element_type(self, type_str: str) -> ElementType:
        """Map string type to ElementType enum"""
        type_mapping = {
            "face": ElementType.FACE,
            "product": ElementType.PRODUCT,
            "text": ElementType.TEXT,
            "logo": ElementType.LOGO,
            "object": ElementType.OBJECT,
            "person": ElementType.PERSON,
            "background": ElementType.BACKGROUND
        }
        return type_mapping.get(type_str.lower(), ElementType.OBJECT)
    
    def _create_fallback_analysis(self, content: str) -> Dict:
        """Create fallback analysis when JSON parsing fails"""
        # Try to extract useful information from the text
        elements = []
        
        # Look for common keywords to create basic elements
        if any(word in content.lower() for word in ['face', 'person', 'people']):
            elements.append({
                "type": "person",
                "confidence": 0.7,
                "bounding_box": {"x": 0.2, "y": 0.2, "width": 0.6, "height": 0.6},
                "description": "Person detected in image",
                "attributes": {"source": "text_analysis"}
            })
        
        if any(word in content.lower() for word in ['text', 'writing', 'words']):
            elements.append({
                "type": "text",
                "confidence": 0.6,
                "bounding_box": {"x": 0.1, "y": 0.8, "width": 0.8, "height": 0.1},
                "description": "Text content detected",
                "attributes": {"source": "text_analysis"}
            })
        
        if not elements:
            elements.append({
                "type": "object",
                "confidence": 0.5,
                "bounding_box": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
                "description": "General content detected",
                "attributes": {"source": "fallback_analysis"}
            })
        
        return {
            "elements": elements,
            "metadata": {
                "dimensions": {"width": 1920, "height": 1080},
                "quality_assessment": "medium",
                "analysis_method": "text_fallback"
            }
        }
    
    def _create_fallback_elements(self) -> List[DetectedElement]:
        """Create fallback elements when parsing fails"""
        return [
            DetectedElement(
                type=ElementType.OBJECT,
                confidence=0.7,
                bounding_box={"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
                description="Content detected (Gemini fallback)",
                attributes={"method": "fallback", "provider": "gemini"}
            )
        ]
    
    def _create_fallback_metadata(self) -> Dict[str, Any]:
        """Create fallback metadata when parsing fails"""
        return {
            "quality_assessment": "medium",
            "analysis_method": "fallback",
            "provider": self.provider_name,
            "style": "unknown"
        }
    
    def _create_fallback_moderation(self) -> ModerationResult:
        """Create fallback moderation result"""
        return ModerationResult(
            category=ModerationCategory.SAFE,
            confidence=0.8,
            flagged=False,
            categories={
                "safe": 0.8,
                "nsfw": 0.2,
                "violence": 0.0,
                "hate": 0.0,
                "harassment": 0.0,
                "self_harm": 0.0
            },
            reason="Fallback classification"
        )
    
    def _analyze_text_for_moderation(self, text: str) -> ModerationResult:
        """Analyze text content for moderation cues"""
        text_lower = text.lower()
        
        categories = {
            "safe": 0.8,
            "nsfw": 0.2,
            "violence": 0.0,
            "hate": 0.0,
            "harassment": 0.0,
            "self_harm": 0.0
        }
        
        # Adjust scores based on keywords
        if any(word in text_lower for word in ['inappropriate', 'nsfw', 'sexual', 'explicit']):
            categories["nsfw"] = 0.7
            categories["safe"] = 0.3
        
        if any(word in text_lower for word in ['violence', 'violent', 'weapon', 'blood']):
            categories["violence"] = 0.6
            categories["safe"] = 0.4
        
        if any(word in text_lower for word in ['hate', 'discrimination', 'offensive']):
            categories["hate"] = 0.5
            categories["safe"] = 0.5
        
        # Determine primary category
        primary_category = max(categories.items(), key=lambda x: x[1])
        
        return ModerationResult(
            category=ModerationCategory(primary_category[0]),
            confidence=primary_category[1],
            flagged=primary_category[1] > 0.5 and primary_category[0] != "safe",
            categories=categories,
            reason="Text-based analysis"
        )
    
    def _resize_image(self, image_path: str, strategy: AdaptationStrategy) -> str:
        """Resize image with the provided strategy"""

        output_path = resize(image_path, strategy.target_width, strategy.target_height, provider=self.provider_name, keep_temp=True)
        return output_path  # Return path to resized image