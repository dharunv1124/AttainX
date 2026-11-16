"""
Domain-specific exceptions for CO calculation and validation.
"""


class DomainValidationError(ValueError):
    """Base exception for all domain validation failures."""
    pass


class InvalidExamConfigurationError(DomainValidationError):
    """Raised when exam metadata or covered CO configuration is invalid."""
    pass


class InvalidQuestionConfigurationError(DomainValidationError):
    """Raised when question parameters, mappings, or maximum marks are invalid."""
    pass


class InvalidMarkError(DomainValidationError):
    """Raised when a student's obtained mark violates domain constraints (e.g. negative or exceeds max)."""
    pass


class IncompleteDataError(DomainValidationError):
    """
    Raised when required data for calculation is incomplete or missing,
    ensuring the domain engine does not silently invent an academic policy.
    """
    pass
