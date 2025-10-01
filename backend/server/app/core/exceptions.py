"""
Custom exceptions for the application
"""


class AppException(Exception):
    """Base application exception"""
    pass


class NotFoundError(AppException):
    """Raised when a resource is not found"""
    pass


class ForbiddenError(AppException):
    """Raised when access to a resource is forbidden"""
    pass


class ValidationError(AppException):
    """Raised when validation fails"""
    pass


class AuthenticationError(AppException):
    """Raised when authentication fails"""
    pass


class AuthorizationError(AppException):
    """Raised when authorization fails"""
    pass