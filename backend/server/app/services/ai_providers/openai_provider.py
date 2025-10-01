"""
OpenAI Provider implementation for image analysis and processing
"""
import asyncio
import base64
import json
import time
from typing import List, Dict, Any
from pathlib import Path
import aiohttp
import io

from .resizer.resizer import resize
from .base import AIProvider, ImageAnalysis, DetectedElement, ModerationResult, AdaptationStrategy
from .base import ElementType, ModerationCategory
from .exceptions import AIProviderError, RateLimitError, AuthenticationError, QuotaExceededError


class OpenAIProvider(AIProvider):
    """OpenAI provider implementation using GPT-4 Vision and moderation APIs"""
    
    def __init__(self, api_key: str, model: str = "gpt-4.1", **kwargs):
        super().__init__(api_key, **kwargs)
        self.model = model
        self.base_url = "https://api.openai.com/v1"
        self.timeout = kwargs.get('timeout', 60)
        self.max_requests_per_minute = kwargs.get('max_requests_per_minute', 60)
    
    @property
    def provider_name(self) -> str:
        return "openai"
    
    @property
    def supported_formats(self) -> List[str]:
        return ["jpg", "jpeg", "png", "webp"]
    
    async def analyze_image(self, image_path: str) -> ImageAnalysis:
        """Analyze image using OpenAI GPT-4 Vision API"""
        self.validate_image(image_path)
        start_time = time.time()
        
        # Get image analysis and moderation in parallel
        analysis_task = self._analyze_with_vision(image_path)
        moderation_task = self.moderate_content(image_path)
        
        elements, metadata = await analysis_task
        moderation = await moderation_task
        
        processing_time = time.time() - start_time
        
        return ImageAnalysis(
            detected_elements=elements,
            moderation=moderation,
            metadata=metadata,
            processing_time=processing_time,
            provider=self.provider_name
        )
    
    async def detect_elements(self, image_path: str) -> List[DetectedElement]:
        """Detect elements using OpenAI Vision API"""
        self.validate_image(image_path)
        elements, _ = await self._analyze_with_vision(image_path)
        return elements
    
    async def moderate_content(self, image_path: str) -> ModerationResult:
        """Moderate content using OpenAI Moderation API"""
        self.validate_image(image_path)
        
        # Convert image to base64
        image_b64 = self._encode_image(image_path)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Use vision API for image moderation since OpenAI doesn't have direct image moderation
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Analyze this image for content safety. Classify it as safe, nsfw, violence, hate, harassment, or self_harm. Provide confidence scores for each category as percentages."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 300
        }
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                async with session.post(f"{self.base_url}/chat/completions", headers=headers, json=payload) as response:
                    await self._handle_response_errors(response)
                    result = await response.json()
                    
                    return self._parse_moderation_response(result)
        
        except aiohttp.ClientError as e:
            raise AIProviderError(f"OpenAI API request failed: {e}")
    
    async def apply_adaptation(self, image_path: str, strategy: AdaptationStrategy) -> str:
        """Apply adaptation strategy using image processing"""
        self.validate_image(image_path)

        print(f"Applying adaptation strategy: {strategy.target_width}x{strategy.target_height} to {image_path}")
        return self._resize_image(image_path, strategy)
    
    async def _analyze_with_vision(self, image_path: str) -> tuple[List[DetectedElement], Dict[str, Any]]:
        """Analyze image using GPT-4 Vision API"""
        image_b64 = self._encode_image(image_path)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """Analyze this image and provide a detailed JSON response with the following structure:
                            {
                                "elements": [
                                    {
                                        "type": "face|product|text|logo|object|person|background",
                                        "confidence": 0.95,
                                        "bounding_box": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
                                        "description": "detailed description",
                                        "attributes": {"key": "value"}
                                    }
                                ],
                                "metadata": {
                                    "dimensions": {"width": 1920, "height": 1080},
                                    "dominant_colors": ["#FF0000", "#00FF00"],
                                    "style": "modern|vintage|minimalist|etc",
                                    "composition": "description of layout",
                                    "quality_assessment": "high|medium|low"
                                }
                            }
                            
                            Be precise with bounding boxes (0-1 normalized coordinates) and confidence scores."""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 1000
        }
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                print(f"Sending image analysis request to OpenAI Vision API for {image_path}")
                async with session.post(f"{self.base_url}/chat/completions", headers=headers, json=payload) as response:
                    await self._handle_response_errors(response)
                    result = await response.json()
                    return self._parse_vision_response(result)
        
        except aiohttp.ClientError as e:
            print("Error during OpenAI Vision API call:", e)
            raise AIProviderError(f"OpenAI API request failed: {e}")
    
    def _encode_image(self, image_path: str) -> str:
        """Encode image to base64 string"""
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            raise AIProviderError(f"Failed to encode image: {e}")
    
    async def _handle_response_errors(self, response: aiohttp.ClientResponse):
        """Handle OpenAI API response errors"""
        if response.status == 200:
            return
        
        try:
            error_data = await response.json()
            error_message = error_data.get('error', {}).get('message', 'Unknown error')
        except:
            error_message = f"HTTP {response.status}"
        
        if response.status == 401:
            raise AuthenticationError(f"OpenAI authentication failed: {error_message}")
        elif response.status == 429:
            # Extract retry-after header if available
            retry_after = response.headers.get('retry-after')
            retry_after = int(retry_after) if retry_after else None
            raise RateLimitError(f"OpenAI rate limit exceeded: {error_message}", retry_after)
        elif response.status == 402:
            raise QuotaExceededError(f"OpenAI quota exceeded: {error_message}")
        else:
            raise AIProviderError(f"OpenAI API error {response.status}: {error_message}")
    
    def _parse_vision_response(self, response: Dict) -> tuple[List[DetectedElement], Dict[str, Any]]:
        """Parse OpenAI Vision API response"""
        try:
            content = response['choices'][0]['message']['content']
            
            # Try to extract JSON from the response
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                data = json.loads(json_str)
            else:
                # Fallback: create mock data if JSON parsing fails
                data = self._create_fallback_analysis(content)
            
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
        
        except (json.JSONDecodeError, KeyError) as e:
            # Fallback to basic analysis
            return self._create_fallback_elements(), self._create_fallback_metadata()
    
    def _parse_moderation_response(self, response: Dict) -> ModerationResult:
        """Parse moderation response from OpenAI"""
        try:
            content = response['choices'][0]['message']['content'].lower()
            
            # Simple keyword-based classification
            categories = {
                "safe": 0.9,
                "nsfw": 0.1,
                "violence": 0.0,
                "hate": 0.0,
                "harassment": 0.0,
                "self_harm": 0.0
            }
            
            # Adjust scores based on content
            if any(word in content for word in ['nsfw', 'sexual', 'nude', 'explicit']):
                categories["nsfw"] = 0.8
                categories["safe"] = 0.2
            
            if any(word in content for word in ['violence', 'violent', 'blood', 'weapon']):
                categories["violence"] = 0.7
                categories["safe"] = 0.3
            
            # Determine primary category
            primary_category = max(categories.items(), key=lambda x: x[1])
            
            return ModerationResult(
                category=ModerationCategory(primary_category[0]),
                confidence=primary_category[1],
                flagged=primary_category[1] > 0.5 and primary_category[0] != "safe",
                categories=categories
            )
        
        except Exception:
            # Fallback to safe classification
            return ModerationResult(
                category=ModerationCategory.SAFE,
                confidence=0.9,
                flagged=False,
                categories={"safe": 0.9, "nsfw": 0.1, "violence": 0.0, "hate": 0.0, "harassment": 0.0, "self_harm": 0.0}
            )
    
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
        return {
            "elements": [
                {
                    "type": "object",
                    "confidence": 0.7,
                    "bounding_box": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
                    "description": "General content detected",
                    "attributes": {"source": "fallback_analysis"}
                }
            ],
            "metadata": {
                "dimensions": {"width": 1920, "height": 1080},
                "quality_assessment": "medium",
                "analysis_method": "fallback"
            }
        }
    
    def _create_fallback_elements(self) -> List[DetectedElement]:
        """Create fallback elements when parsing fails"""
        return [
            DetectedElement(
                type=ElementType.OBJECT,
                confidence=0.7,
                bounding_box={"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
                description="Content detected (fallback)",
                attributes={"method": "fallback"}
            )
        ]
    
    def _create_fallback_metadata(self) -> Dict[str, Any]:
        """Create fallback metadata when parsing fails"""
        return {
            "quality_assessment": "medium",
            "analysis_method": "fallback",
            "provider": self.provider_name
        }

    def _resize_image(self, image_path: str, strategy: AdaptationStrategy) -> str:
        """Resize image with the provided strategy"""

        output_path = resize(image_path, strategy.target_width, strategy.target_height, provider=self.provider_name, keep_temp=False)
        return output_path  # Return path to resized image