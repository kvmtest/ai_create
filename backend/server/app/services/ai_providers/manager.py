"""
AI Provider Manager - Main interface for AI provider operations
"""
from typing import Optional, List, Dict, Any
import asyncio
import logging
import structlog
from .base import AIProvider, ImageAnalysis, DetectedElement, ModerationResult, AdaptationStrategy
from .factory import AIProviderFactory, RetryHandler, LoadBalancer
from .config import config_manager
from .exceptions import AIProviderError, ServiceUnavailableError

logger = structlog.get_logger()


class AIProviderManager:
    """
    Main manager for AI provider operations with failover and load balancing
    """
    
    def __init__(self):
        self.retry_handler = RetryHandler(max_retries=3, base_delay=1.0, max_delay=60.0)
        self.load_balancer = None
        self._initialize_load_balancer()
    
    def _initialize_load_balancer(self):
        """Initialize load balancer with enabled providers"""
        enabled_providers = config_manager.get_enabled_providers()
        if enabled_providers:
            self.load_balancer = LoadBalancer(enabled_providers)
    
    async def analyze_image(
        self, 
        image_path: str, 
        provider_name: Optional[str] = None
    ) -> ImageAnalysis:
        """
        Analyze an image using the specified or best available provider
        
        Args:
            image_path: Path to the image file
            provider_name: Specific provider to use (optional)
            
        Returns:
            ImageAnalysis result
            
        Raises:
            AIProviderError: If analysis fails
        """
        logger.info(
            "AI Manager starting image analysis",
            image_path=image_path,
            requested_provider=provider_name,
            available_providers=config_manager.get_enabled_providers() if hasattr(config_manager, 'get_enabled_providers') else "unknown"
        )
        
        try:
            if provider_name:
                # Use specific provider
                logger.info("Using specific AI provider", provider=provider_name, image_path=image_path)
                provider = self._get_provider(provider_name)
                result = await self.retry_handler.execute_with_retry(
                    provider.analyze_image, image_path
                )
                logger.info(
                    "AI analysis completed with specific provider",
                    provider=provider_name,
                    image_path=image_path,
                    processing_time=result.processing_time,
                    elements_count=len(result.detected_elements)
                )
                return result
            else:
                # Use load balancer to select provider
                logger.info("Using load balancer for provider selection", image_path=image_path)
                result = await self._analyze_with_failover(image_path)
                logger.info(
                    "AI analysis completed with load balancer",
                    actual_provider=result.provider,
                    image_path=image_path,
                    processing_time=result.processing_time,
                    elements_count=len(result.detected_elements)
                )
                return result
        except Exception as e:
            logger.error(
                "AI Manager analysis failed",
                image_path=image_path,
                requested_provider=provider_name,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    async def detect_elements(
        self, 
        image_path: str, 
        provider_name: Optional[str] = None
    ) -> List[DetectedElement]:
        """
        Detect elements in an image
        
        Args:
            image_path: Path to the image file
            provider_name: Specific provider to use (optional)
            
        Returns:
            List of detected elements
        """
        if provider_name:
            provider = self._get_provider(provider_name)
            return await self.retry_handler.execute_with_retry(
                provider.detect_elements, image_path
            )
        else:
            return await self._detect_elements_with_failover(image_path)
    
    async def moderate_content(
        self, 
        image_path: str, 
        provider_name: Optional[str] = None
    ) -> ModerationResult:
        """
        Moderate image content for safety
        
        Args:
            image_path: Path to the image file
            provider_name: Specific provider to use (optional)
            
        Returns:
            ModerationResult
        """
        if provider_name:
            provider = self._get_provider(provider_name)
            return await self.retry_handler.execute_with_retry(
                provider.moderate_content, image_path
            )
        else:
            return await self._moderate_with_failover(image_path)
    
    async def apply_adaptation(
        self, 
        image_path: str, 
        strategy: AdaptationStrategy,
        provider: Optional[str] = None
    ) -> str:
        """
        Apply adaptation strategy to an image
        
        Args:
            image_path: Path to the source image
            strategy: Adaptation strategy
            provider: Specific provider to use (optional)
            
        Returns:
            Path to adapted image
        """
        if provider:
            provider_instance = self._get_provider(provider)
            return await self.retry_handler.execute_with_retry(
                provider_instance.apply_adaptation, image_path, strategy
            )
        else:
            return await self._adapt_with_failover(image_path, strategy)
    
    def _get_provider(self, provider_name: str) -> AIProvider:
        """Get a provider instance"""
        config = config_manager.get_provider_dict(provider_name)
        if not config:
            raise AIProviderError(f"Provider {provider_name} not configured")
        
        return AIProviderFactory.get_provider(provider_name, config)
    
    async def _analyze_with_failover(self, image_path: str) -> ImageAnalysis:
        """Analyze image with automatic failover"""
        if not self.load_balancer:
            raise AIProviderError("No providers available")
        
        providers_tried = []
        last_exception = None
        
        # Try providers in order of priority
        for provider_name in config_manager.get_providers_by_priority():
            if provider_name in providers_tried:
                continue
            
            try:
                provider = self._get_provider(provider_name)
                result = await self.retry_handler.execute_with_retry(
                    provider.analyze_image, image_path
                )
                logger.info(f"Successfully analyzed image using {provider_name}")
                return result
            
            except Exception as e:
                last_exception = e
                providers_tried.append(provider_name)
                self.load_balancer.record_error(provider_name)
                logger.warning(f"Provider {provider_name} failed: {e}")
                continue
        
        # If all providers failed
        raise AIProviderError(
            f"All providers failed. Tried: {', '.join(providers_tried)}. "
            f"Last error: {last_exception}"
        )
    
    async def _detect_elements_with_failover(self, image_path: str) -> List[DetectedElement]:
        """Detect elements with automatic failover"""
        if not self.load_balancer:
            raise AIProviderError("No providers available")
        
        for provider_name in config_manager.get_providers_by_priority():
            try:
                provider = self._get_provider(provider_name)
                return await self.retry_handler.execute_with_retry(
                    provider.detect_elements, image_path
                )
            except Exception as e:
                self.load_balancer.record_error(provider_name)
                logger.warning(f"Provider {provider_name} failed for element detection: {e}")
                continue
        
        raise AIProviderError("All providers failed for element detection")
    
    async def _moderate_with_failover(self, image_path: str) -> ModerationResult:
        """Moderate content with automatic failover"""
        if not self.load_balancer:
            raise AIProviderError("No providers available")
        
        for provider_name in config_manager.get_providers_by_priority():
            try:
                provider = self._get_provider(provider_name)
                return await self.retry_handler.execute_with_retry(
                    provider.moderate_content, image_path
                )
            except Exception as e:
                self.load_balancer.record_error(provider_name)
                logger.warning(f"Provider {provider_name} failed for content moderation: {e}")
                continue
        
        raise AIProviderError("All providers failed for content moderation")
    
    async def _adapt_with_failover(self, image_path: str, strategy: AdaptationStrategy) -> str:
        """Apply adaptation with automatic failover"""
        if not self.load_balancer:
            raise AIProviderError("No providers available")
        
        for provider_name in config_manager.get_providers_by_priority():
            try:
                provider = self._get_provider(provider_name)
                return await self.retry_handler.execute_with_retry(
                    provider.apply_adaptation, image_path, strategy
                )
            except Exception as e:
                self.load_balancer.record_error(provider_name)
                logger.warning(f"Provider {provider_name} failed for adaptation: {e}")
                continue
        
        raise AIProviderError("All providers failed for image adaptation")
    
    def get_provider_stats(self) -> Dict:
        """Get statistics for all providers"""
        if not self.load_balancer:
            return {}
        
        return self.load_balancer.get_stats()
    
    def get_available_providers(self) -> List[str]:
        """Get list of available provider names"""
        return config_manager.get_enabled_providers()
    
    def health_check(self) -> Dict[str, bool]:
        """Check health of all configured providers"""
        health_status = {}
        
        for provider_name in config_manager.get_enabled_providers():
            try:
                config = config_manager.get_provider_dict(provider_name)
                provider = AIProviderFactory.get_provider(provider_name, config)
                # Basic validation - check if provider can be instantiated
                health_status[provider_name] = True
            except Exception as e:
                logger.error(f"Health check failed for {provider_name}: {e}")
                health_status[provider_name] = False
        
        return health_status


# Global AI provider manager instance
ai_manager = AIProviderManager()