"""
Centralized logging configuration for the application
"""
import os
import sys
import logging
import structlog
from typing import Any, Dict


def setup_logging(
    log_level: str = "INFO",
    log_format: str = "json"
) -> None:
    """
    Configure structured logging for the application
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Output format ('json' or 'console')
    """
    # Set up stdlib logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper())
    )
    
    # Configure structlog
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]
    
    if log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Get a structured logger instance
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Structured logger instance
    """
    return structlog.get_logger(name)


class LoggerAdapter:
    """Adapter to add context to all log messages"""
    
    def __init__(self, logger: structlog.BoundLogger, **kwargs):
        self.logger = logger
        self.context = kwargs
    
    def bind(self, **kwargs) -> "LoggerAdapter":
        """Add context that will be included in all messages"""
        new_context = {**self.context, **kwargs}
        return LoggerAdapter(self.logger, **new_context)
    
    def _log(self, method: str, event: str, **kwargs):
        """Internal log method"""
        merged_kwargs = {**self.context, **kwargs}
        getattr(self.logger, method)(event, **merged_kwargs)
    
    def debug(self, event: str, **kwargs):
        self._log("debug", event, **kwargs)
    
    def info(self, event: str, **kwargs):
        self._log("info", event, **kwargs)
    
    def warning(self, event: str, **kwargs):
        self._log("warning", event, **kwargs)
    
    def error(self, event: str, **kwargs):
        self._log("error", event, **kwargs)
    
    def critical(self, event: str, **kwargs):
        self._log("critical", event, **kwargs)


# Request ID middleware for tracing
from fastapi import Request
import uuid


async def add_request_id(request: Request, call_next):
    """Middleware to add request ID to all logs"""
    request_id = str(uuid.uuid4())
    
    # Add to request state
    request.state.request_id = request_id
    
    # Bind to logger for this request
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)
    
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    
    return response


# Performance logging decorator
import time
import functools
from typing import Callable


def log_performance(logger: structlog.BoundLogger = None):
    """Decorator to log function performance"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            func_logger = logger or get_logger(func.__module__)
            
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                
                func_logger.info(
                    "Function completed",
                    function=func.__name__,
                    duration_seconds=round(duration, 3),
                    success=True
                )
                
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                
                func_logger.error(
                    "Function failed",
                    function=func.__name__,
                    duration_seconds=round(duration, 3),
                    error=str(e),
                    error_type=type(e).__name__
                )
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            func_logger = logger or get_logger(func.__module__)
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                func_logger.info(
                    "Function completed",
                    function=func.__name__,
                    duration_seconds=round(duration, 3),
                    success=True
                )
                
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                
                func_logger.error(
                    "Function failed",
                    function=func.__name__,
                    duration_seconds=round(duration, 3),
                    error=str(e),
                    error_type=type(e).__name__
                )
                raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# Initialize logging on import
import asyncio
setup_logging(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    log_format=os.getenv("LOG_FORMAT", "json")
)
