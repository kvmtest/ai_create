"""
AI Provider configuration management
"""
from typing import Dict, List, Optional
from dataclasses import dataclass
import os
from app.core.config import settings


@dataclass
class ProviderConfig:
    """Configuration for an AI provider"""
    name: str
    api_key: str
    model: Optional[str] = None
    max_requests_per_minute: int = 60
    timeout: int = 60
    enabled: bool = True
    priority: int = 1  # Lower number = higher priority


class AIProviderConfigManager:
    """Manages AI provider configurations"""
    
    def __init__(self):
        self._configs: Dict[str, ProviderConfig] = {}
        self._load_default_configs()
    
    def _load_default_configs(self):
        """Load default configurations from environment variables"""
        
        # OpenAI Configuration
        openai_key = getattr(settings, 'OPENAI_API_KEY', None) or os.getenv('OPENAI_API_KEY')
        if openai_key:
            self._configs['openai'] = ProviderConfig(
                name='openai',
                api_key=openai_key,
                model=os.getenv('OPENAI_MODEL', 'gpt-4.1'),
                max_requests_per_minute=int(os.getenv('OPENAI_RPM', '60')),
                timeout=int(os.getenv('OPENAI_TIMEOUT', '60')),
                enabled=os.getenv('OPENAI_ENABLED', 'false').lower() == 'true',  # Disabled by default
                priority=int(os.getenv('OPENAI_PRIORITY', '2'))
            )
        
        # Gemini Configuration (primary provider)
        gemini_key = getattr(settings, 'GEMINI_API_KEY', None) or os.getenv('GEMINI_API_KEY')
        if gemini_key:
            self._configs['gemini'] = ProviderConfig(
                name='gemini',
                api_key=gemini_key,
                model=os.getenv('GEMINI_MODEL', 'gemini-2.5-flash'),
                max_requests_per_minute=int(os.getenv('GEMINI_RPM', '15')),  # Lower rate for better reliability
                timeout=int(os.getenv('GEMINI_TIMEOUT', '60')),  # Increased timeout for multiple files
                enabled=os.getenv('GEMINI_ENABLED', 'true').lower() == 'true',
                priority=int(os.getenv('GEMINI_PRIORITY', '1'))
            )
        
        # Claude Configuration
        claude_key = getattr(settings, 'CLAUDE_API_KEY', None) or os.getenv('CLAUDE_API_KEY')
        if claude_key:
            self._configs['claude'] = ProviderConfig(
                name='claude',
                api_key=claude_key,
                model=os.getenv('CLAUDE_MODEL', 'claude-3-vision'),
                max_requests_per_minute=int(os.getenv('CLAUDE_RPM', '60')),
                timeout=int(os.getenv('CLAUDE_TIMEOUT', '60')),
                enabled=os.getenv('CLAUDE_ENABLED', 'false').lower() == 'true',  # Disabled by default
                priority=int(os.getenv('CLAUDE_PRIORITY', '3'))
            )
        

    
    def get_config(self, provider_name: str) -> Optional[ProviderConfig]:
        """Get configuration for a specific provider"""
        return self._configs.get(provider_name)
    
    def get_all_configs(self) -> Dict[str, ProviderConfig]:
        """Get all provider configurations"""
        return self._configs.copy()
    
    def get_enabled_providers(self) -> List[str]:
        """Get list of enabled provider names"""
        return [name for name, config in self._configs.items() if config.enabled]
    
    def get_providers_by_priority(self) -> List[str]:
        """Get providers sorted by priority (lowest number = highest priority)"""
        enabled_configs = [(name, config) for name, config in self._configs.items() if config.enabled]
        sorted_configs = sorted(enabled_configs, key=lambda x: x[1].priority)
        return [name for name, _ in sorted_configs]
    
    def add_config(self, config: ProviderConfig):
        """Add or update a provider configuration"""
        self._configs[config.name] = config
    
    def remove_config(self, provider_name: str):
        """Remove a provider configuration"""
        if provider_name in self._configs:
            del self._configs[provider_name]
    
    def update_config(self, provider_name: str, **kwargs):
        """Update specific fields of a provider configuration"""
        if provider_name in self._configs:
            config = self._configs[provider_name]
            for key, value in kwargs.items():
                if hasattr(config, key):
                    setattr(config, key, value)
    
    def get_default_provider(self) -> Optional[str]:
        """Get the default provider (highest priority enabled provider)"""
        providers = self.get_providers_by_priority()
        return providers[0] if providers else None
    
    def validate_config(self, provider_name: str) -> bool:
        """Validate that a provider configuration is complete and valid"""
        config = self.get_config(provider_name)
        if not config:
            return False
        
        # Check required fields
        if not config.api_key:
            return False
        
        if not config.name:
            return False
        
        return True
    
    def get_provider_dict(self, provider_name: str) -> Dict:
        """Get provider configuration as dictionary for factory"""
        config = self.get_config(provider_name)
        if not config:
            return {}
        
        return {
            'api_key': config.api_key,
            'model': config.model,
            'timeout': config.timeout,
            'max_requests_per_minute': config.max_requests_per_minute
        }


# Global configuration manager instance
config_manager = AIProviderConfigManager()