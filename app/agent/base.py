"""
Base AI agent class providing common functionality for all AI agents.

This module defines an abstract base class that all specific AI agents inherit from,
providing common methods for LLM client management (Gemini), error handling, logging, and retry logic.
"""

import logging
import time
from abc import ABC
from typing import Any, Callable, TypeVar

import google.generativeai as genai

from app.config import AppConfig, GeminiConfig


T = TypeVar("T")


class BaseAgent(ABC):
    """
    Abstract base class for all AI agents.
    
    Provides common functionality including:
    - Shared Gemini configuration
    - Error handling for API failures
    - Logging helpers
    - Retry logic for transient failures
    - Consistent interface for different operations
    
    Subclasses must implement agent-specific methods.
    """

    def __init__(self, config: AppConfig) -> None:
        """
        Initialize base agent with configuration and Gemini client.
        
        Args:
            config: Application configuration containing Gemini settings
        """
        self.config: GeminiConfig = config.gemini
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Configure Gemini client with API key and model from config
        genai.configure(api_key=self.config.api_key)
        self.model = self.config.model

    def _log_info(self, message: str, **kwargs: Any) -> None:
        """
        Log an informational message with optional context.
        
        Args:
            message: Log message
            **kwargs: Additional context to include in log
        """
        if kwargs:
            context = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            self.logger.info(f"{message} | {context}")
        else:
            self.logger.info(message)

    def _log_error(
        self, message: str, exception: Exception | None = None, **kwargs: Any
    ) -> None:
        """
        Log an error message with optional exception and context.
        
        Args:
            message: Error message
            exception: Optional exception object
            **kwargs: Additional context to include in log
        """
        if kwargs:
            context = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            full_message = f"{message} | {context}"
        else:
            full_message = message

        if exception:
            self.logger.error(f"{full_message} | Exception: {exception}", exc_info=True)
        else:
            self.logger.error(full_message)

    def _handle_api_error(
        self, error: Exception, operation: str = "API call"
    ) -> None:
        """
        Handle LLM API errors with appropriate logging and error messages.
        
        Args:
            error: The exception that occurred
            operation: Description of the operation that failed
            
        Raises:
            Exception: Re-raises the error after logging
        """
        self._log_error(
            f"{operation} failed",
            exception=error,
            operation=operation,
        )
        raise

    def _retry_with_backoff(
        self,
        func: Callable[[], T],
        max_retries: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0,
        operation: str = "API call",
    ) -> T:
        """
        Execute a function with exponential backoff retry logic.
        
        Handles transient failures by retrying with increasing delays.
        Specifically handles rate limit errors with longer delays.
        
        Args:
            func: Function to execute (should be a callable that takes no arguments)
            max_retries: Maximum number of retry attempts (default: 3)
            initial_delay: Initial delay in seconds before first retry (default: 1.0)
            backoff_factor: Multiplier for delay between retries (default: 2.0)
            operation: Description of operation for logging (default: "API call")
            
        Returns:
            Result of the function call
            
        Raises:
            Exception: The last exception if all retries fail
        """
        delay = initial_delay
        last_exception: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    self._log_info(
                        f"{operation} failed, retrying in {delay:.1f}s",
                        attempt=attempt + 1,
                        max_retries=max_retries + 1,
                    )
                    time.sleep(delay)
                    delay *= backoff_factor
                else:
                    self._handle_api_error(e, operation)

        # If we exhausted retries, raise the last exception
        if last_exception:
            self._handle_api_error(last_exception, operation)
        raise RuntimeError(f"Failed to execute {operation} after {max_retries + 1} attempts")

    def _call_llm(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Make a call to the LLM (Gemini) API with error handling and retry logic.
        
        Args:
            messages: List of message dictionaries for the chat completion
            temperature: Sampling temperature (default: 0.7)
            max_tokens: Maximum tokens in response (None for model default)
            **kwargs: Additional arguments to pass to the underlying API
            
        Returns:
            Content of the assistant's message response
            
        Raises:
            Exception: If the API call fails after retries
        """
        def _make_request() -> str:
            """Inner function to make the actual API request."""
            # Convert OpenAI-style messages into a single prompt string
            prompt_parts: list[str] = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                prompt_parts.append(f"{role.upper()}: {content}")
            prompt = "\n\n".join(prompt_parts)

            model = genai.GenerativeModel(self.model)
            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                } if max_tokens is not None else {
                    "temperature": temperature,
                },
                **kwargs,
            )

            # Gemini responses typically expose text via .text
            return getattr(response, "text", "") or ""

        return self._retry_with_backoff(
            _make_request,
            operation=f"Gemini API call (model: {self.model})",
        )

