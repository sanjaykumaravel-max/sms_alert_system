"""
Custom Exceptions for SMS Alert App

This module defines custom exceptions for better error handling
and API responses.
"""

from typing import Dict, Any, Optional
from fastapi import HTTPException


class SMSAlertException(Exception):
    """Base exception for SMS Alert application."""

    def __init__(self, message: str, status_code: int = 500, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(SMSAlertException):
    """Exception raised for validation errors."""

    def __init__(self, message: str, field: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=400, details=details or {})
        if field:
            self.details["field"] = field


class NotFoundError(SMSAlertException):
    """Exception raised when a resource is not found."""

    def __init__(self, resource: str, resource_id: Any, details: Optional[Dict[str, Any]] = None):
        message = f"{resource} with id '{resource_id}' not found"
        super().__init__(message, status_code=404, details=details or {})
        self.resource = resource
        self.resource_id = resource_id


class AuthenticationError(SMSAlertException):
    """Exception raised for authentication failures."""

    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=401, details=details or {})


class AuthorizationError(SMSAlertException):
    """Exception raised for authorization failures."""

    def __init__(self, message: str = "Insufficient permissions", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=403, details=details or {})


class SMSServiceError(SMSAlertException):
    """Exception raised for SMS service failures."""

    def __init__(self, message: str, provider: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=502, details=details or {})
        if provider:
            self.details["provider"] = provider


class DatabaseError(SMSAlertException):
    """Exception raised for database operation failures."""

    def __init__(self, message: str, operation: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=500, details=details or {})
        if operation:
            self.details["operation"] = operation


class ExternalServiceError(SMSAlertException):
    """Exception raised for external service failures."""

    def __init__(self, service: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(f"{service}: {message}", status_code=502, details=details or {})
        self.service = service


def handle_sms_alert_exception(exc: SMSAlertException) -> HTTPException:
    """Convert SMSAlertException to FastAPI HTTPException."""
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "error": exc.__class__.__name__,
            "message": exc.message,
            "details": exc.details
        }
    )


# Utility functions for common validations
def validate_phone_number(phone: str) -> str:
    """Validate and format phone number."""
    if not phone:
        raise ValidationError("Phone number is required", field="phone")

    # Remove spaces and ensure it starts with +
    phone = phone.strip()
    if not phone.startswith('+'):
        phone = '+' + phone

    # Basic validation - should be at least 10 digits after +
    if len(phone) < 11:
        raise ValidationError("Invalid phone number format", field="phone")

    return phone


def validate_machine_id(machine_id: str) -> str:
    """Validate machine ID format."""
    if not machine_id:
        raise ValidationError("Machine ID is required", field="id")

    machine_id = machine_id.strip().upper()
    if len(machine_id) < 2:
        raise ValidationError("Machine ID too short", field="id")

    return machine_id


def validate_required_field(value: Any, field_name: str) -> Any:
    """Validate that a required field is not empty."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValidationError(f"{field_name} is required", field=field_name)

    return value