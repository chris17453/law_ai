"""LLM client abstraction for multiple providers."""

from abc import ABC, abstractmethod
from typing import Generator, List, Dict, Optional

from .config import Config


class LLMClient(ABC):
    """Abstract base class for LLM clients."""
    
    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        stream: bool = True
    ) -> Generator[str, None, None] | str:
        """Send a chat completion request."""
        pass
    
    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the client is properly configured."""
        pass


class AzureClient(LLMClient):
    """Azure OpenAI client."""
    
    def __init__(self, config: Config):
        self.config = config
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            from openai import AzureOpenAI
            self._client = AzureOpenAI(
                azure_endpoint=self.config.azure_endpoint,
                api_key=self.config.azure_api_key,
                api_version=self.config.azure_api_version,
            )
        return self._client
    
    def is_configured(self) -> bool:
        return bool(self.config.azure_endpoint and self.config.azure_api_key)
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        stream: bool = True
    ) -> Generator[str, None, None] | str:
        client = self._get_client()
        
        response = client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            stream=stream,
        )
        
        if stream:
            def generate():
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
            return generate()
        else:
            return response.choices[0].message.content


class OpenAIClient(LLMClient):
    """OpenAI client."""
    
    def __init__(self, config: Config):
        self.config = config
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            kwargs = {"api_key": self.config.openai_api_key}
            if self.config.openai_base_url:
                kwargs["base_url"] = self.config.openai_base_url
            self._client = OpenAI(**kwargs)
        return self._client
    
    def is_configured(self) -> bool:
        return bool(self.config.openai_api_key)
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        stream: bool = True
    ) -> Generator[str, None, None] | str:
        client = self._get_client()
        
        response = client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            stream=stream,
        )
        
        if stream:
            def generate():
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
            return generate()
        else:
            return response.choices[0].message.content


class AnthropicClient(LLMClient):
    """Anthropic Claude client."""
    
    def __init__(self, config: Config):
        self.config = config
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)
        return self._client
    
    def is_configured(self) -> bool:
        return bool(self.config.anthropic_api_key)
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        stream: bool = True
    ) -> Generator[str, None, None] | str:
        client = self._get_client()
        
        # Extract system message
        system = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                chat_messages.append(msg)
        
        if stream:
            def generate():
                with client.messages.stream(
                    model=self.config.model,
                    max_tokens=self.config.max_tokens,
                    system=system,
                    messages=chat_messages,
                ) as stream:
                    for text in stream.text_stream:
                        yield text
            return generate()
        else:
            response = client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=system,
                messages=chat_messages,
            )
            return response.content[0].text


def get_llm_client(config: Config) -> LLMClient:
    """Get the appropriate LLM client based on configuration."""
    provider = config.provider.lower()
    
    if provider == "azure":
        client = AzureClient(config)
    elif provider == "openai":
        client = OpenAIClient(config)
    elif provider == "anthropic":
        client = AnthropicClient(config)
    else:
        raise ValueError(f"Unknown provider: {provider}")
    
    if not client.is_configured():
        raise ValueError(
            f"Provider '{provider}' is not configured. "
            f"Run 'law-ai config' to set up your API keys."
        )
    
    return client
