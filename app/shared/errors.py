class AgentSystemError(Exception):
    """Base exception for multi-agent subsystem."""


class RetryableAgentError(AgentSystemError):
    """Error that may succeed after retry."""


class CircuitBreakerOpen(AgentSystemError):
    """Raised when execution is blocked by open circuit breaker."""
