"""
Circuit Breaker pattern for fault tolerance in external API calls
"""
import asyncio
import time
from enum import Enum
from typing import Optional, Callable, Any
from datetime import datetime, timedelta

from src.utils.logging import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Failing, block calls
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures
    
    States:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Too many failures, calls are blocked
    - HALF_OPEN: Testing recovery, limited calls allowed
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception,
        name: Optional[str] = None
    ):
        """
        Initialize circuit breaker
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            expected_exception: Exception type to catch
            name: Optional name for logging
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.name = name or "CircuitBreaker"
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state"""
        return self._state
    
    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)"""
        return self._state == CircuitState.CLOSED
    
    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking calls)"""
        return self._state == CircuitState.OPEN
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self._before_call()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if exc_type is None:
            await self._on_success()
        elif issubclass(exc_type, self.expected_exception):
            await self._on_failure()
            return False  # Propagate exception
        # Don't handle unexpected exceptions
        return False
    
    async def _before_call(self):
        """Check circuit state before allowing call"""
        async with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if we should transition to half-open
                if self._should_attempt_reset():
                    logger.info(f"{self.name}: Attempting reset to HALF_OPEN")
                    self._state = CircuitState.HALF_OPEN
                else:
                    raise CircuitOpenError(
                        f"{self.name}: Circuit is OPEN, calls are blocked"
                    )
    
    async def _on_success(self):
        """Handle successful call"""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info(f"{self.name}: Success in HALF_OPEN, closing circuit")
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._last_failure_time = None
    
    async def _on_failure(self):
        """Handle failed call"""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.utcnow()
            
            if self._state == CircuitState.HALF_OPEN:
                logger.warning(f"{self.name}: Failure in HALF_OPEN, reopening circuit")
                self._state = CircuitState.OPEN
            elif self._failure_count >= self.failure_threshold:
                logger.error(
                    f"{self.name}: Failure threshold reached ({self._failure_count}), "
                    f"opening circuit"
                )
                self._state = CircuitState.OPEN
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if not self._last_failure_time:
            return True
        
        time_since_failure = datetime.utcnow() - self._last_failure_time
        return time_since_failure.total_seconds() >= self.recovery_timeout
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection
        
        Args:
            func: Async function to call
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result of func
            
        Raises:
            CircuitOpenError: If circuit is open
            Exception: If func raises exception
        """
        async with self:
            return await func(*args, **kwargs)
    
    def reset(self):
        """Manually reset the circuit breaker"""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        logger.info(f"{self.name}: Circuit manually reset")
    
    def get_stats(self) -> dict:
        """Get circuit breaker statistics"""
        return {
            'name': self.name,
            'state': self._state.value,
            'failure_count': self._failure_count,
            'last_failure_time': self._last_failure_time.isoformat() if self._last_failure_time else None,
            'failure_threshold': self.failure_threshold,
            'recovery_timeout': self.recovery_timeout
        }


class CircuitOpenError(Exception):
    """Raised when circuit is open and calls are blocked"""
    pass


class MultiCircuitBreaker:
    """Manage multiple circuit breakers for different services"""
    
    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}
    
    def add_breaker(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception
    ) -> CircuitBreaker:
        """Add a new circuit breaker"""
        breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            expected_exception=expected_exception,
            name=name
        )
        self._breakers[name] = breaker
        return breaker
    
    def get_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by name"""
        return self._breakers.get(name)
    
    def get_all_stats(self) -> dict:
        """Get statistics for all circuit breakers"""
        return {
            name: breaker.get_stats()
            for name, breaker in self._breakers.items()
        }
    
    def reset_all(self):
        """Reset all circuit breakers"""
        for breaker in self._breakers.values():
            breaker.reset()


# Global circuit breaker manager
_circuit_manager = MultiCircuitBreaker()


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
    expected_exception: type = Exception
) -> CircuitBreaker:
    """
    Get or create a circuit breaker
    
    Args:
        name: Unique name for the circuit breaker
        failure_threshold: Number of failures before opening
        recovery_timeout: Seconds before attempting recovery
        expected_exception: Exception type to monitor
        
    Returns:
        Circuit breaker instance
    """
    breaker = _circuit_manager.get_breaker(name)
    if not breaker:
        breaker = _circuit_manager.add_breaker(
            name,
            failure_threshold,
            recovery_timeout,
            expected_exception
        )
    return breaker
