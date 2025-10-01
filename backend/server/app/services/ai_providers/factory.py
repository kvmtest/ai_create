"""
AI Provider Factory for creating and managing provider instances
"""
from typing import Dict, Type, Optional
import asyncio
import time
from .base import AIProvider
from .exceptions import AIProviderError, RateLimitError, ServiceUnavailableError


class AIProviderFactory:
    """Factory for creating and managing AI provider instances"""
    
    _providers: Dict[str, Type[AIProvider]] = {}
    _instances: Dict[str, AIProvider] = {}
    
    @classmethod
    def register_provider(cls, name: str, provider_class: Type[AIProvider]):
        """Register a new AI provider class"""
        cls._providers[name] = provider_class
    
    @classmethod
    def create_provider(cls, provider_type: str, config: Dict) -> AIProvider:
        """
        Create an AI provider instance
        
        Args:
            provider_type: Type of provider (openai, gemini, claude)
            config: Configuration dictionary with API keys and settings
            
        Returns:
            AIProvider instance
            
        Raises:
            AIProviderError: If provider type is not supported
        """
        if provider_type not in cls._providers:
            available = ", ".join(cls._providers.keys())
            raise AIProviderError(
                f"Unsupported provider type: {provider_type}. "
                f"Available providers: {available}"
            )
        
        provider_class = cls._providers[provider_type]
        return provider_class(**config)
    
    @classmethod
    def get_provider(cls, provider_type: str, config: Dict) -> AIProvider:
        """
        Get or create a cached provider instance
        
        Args:
            provider_type: Type of provider
            config: Configuration dictionary
            
        Returns:
            AIProvider instance (cached if available)
        """
        cache_key = f"{provider_type}_{hash(str(sorted(config.items())))}"
        
        if cache_key not in cls._instances:
            cls._instances[cache_key] = cls.create_provider(provider_type, config)
        
        return cls._instances[cache_key]
    
    @classmethod
    def list_providers(cls) -> list:
        """List all registered provider types"""
        return list(cls._providers.keys())


class RetryHandler:
    """Handles retry logic with exponential backoff for AI provider calls"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
    
    async def execute_with_retry(self, func, *args, **kwargs):
        """
        Execute a function with retry logic
        
        Args:
            func: Async function to execute
            *args, **kwargs: Arguments to pass to the function
            
        Returns:
            Function result
            
        Raises:
            AIProviderError: If all retries are exhausted
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            
            except RateLimitError as e:
                last_exception = e
                if attempt == self.max_retries:
                    break
                
                # Use retry_after from the exception if available
                delay = e.retry_after if e.retry_after else self._calculate_delay(attempt)
                await asyncio.sleep(delay)
            
            except ServiceUnavailableError as e:
                last_exception = e
                if attempt == self.max_retries:
                    break
                
                delay = self._calculate_delay(attempt)
                await asyncio.sleep(delay)
            
            except AIProviderError as e:
                # Don't retry for other AI provider errors
                raise e
        
        # If we get here, all retries were exhausted
        raise AIProviderError(f"All retries exhausted. Last error: {last_exception}")
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay"""
        delay = self.base_delay * (2 ** attempt)
        return min(delay, self.max_delay)


class LoadBalancer:
    """Simple load balancer for distributing requests across multiple providers"""
    
    def __init__(self, providers: list):
        self.providers = providers
        self.current_index = 0
        self.provider_stats = {provider: {"requests": 0, "errors": 0} for provider in providers}
    
    def get_next_provider(self) -> str:
        """Get the next provider using round-robin strategy"""
        if not self.providers:
            raise AIProviderError("No providers available")
        
        provider = self.providers[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.providers)
        
        self.provider_stats[provider]["requests"] += 1
        return provider
    
    def record_error(self, provider: str):
        """Record an error for a provider"""
        if provider in self.provider_stats:
            self.provider_stats[provider]["errors"] += 1
    
    def get_stats(self) -> Dict:
        """Get provider statistics"""
        return self.provider_stats.copy()
    
    def get_healthiest_provider(self) -> str:
        """Get the provider with the lowest error rate"""
        if not self.providers:
            raise AIProviderError("No providers available")
        
        best_provider = None
        best_error_rate = float('inf')
        
        for provider in self.providers:
            stats = self.provider_stats[provider]
            if stats["requests"] == 0:
                error_rate = 0
            else:
                error_rate = stats["errors"] / stats["requests"]
            
            if error_rate < best_error_rate:
                best_error_rate = error_rate
                best_provider = provider
        
        return best_provider or self.providers[0]