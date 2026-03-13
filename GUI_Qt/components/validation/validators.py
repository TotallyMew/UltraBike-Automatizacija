"""
Validation framework for UltraBike application.

Provides a flexible validation system with custom validators for common input types.
All validators support i18n for localized error messages.
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable
import re


class ValidationResult:
    """Result of a validation operation."""

    def __init__(self, valid: bool, error: str = "", warning: str = ""):
        """
        Initialize validation result.

        Args:
            valid: Whether the validation passed
            error: Error message if validation failed
            warning: Warning message (validation passed but with caveats)
        """
        self.valid = valid
        self.error = error
        self.warning = warning

    def __bool__(self):
        """Allow using ValidationResult in boolean context."""
        return self.valid

    def __repr__(self):
        if self.valid and self.warning:
            return f"ValidationResult(valid=True, warning='{self.warning}')"
        elif not self.valid:
            return f"ValidationResult(valid=False, error='{self.error}')"
        return "ValidationResult(valid=True)"


class BaseValidator(ABC):
    """Abstract base class for all validators."""

    def __init__(self, tr_func: Optional[Callable] = None):
        """
        Initialize validator.

        Args:
            tr_func: Translation function for error messages (i18n.tr or screen.tr)
        """
        self.tr = tr_func if tr_func else lambda key, **kwargs: key

    @abstractmethod
    def validate(self, value) -> ValidationResult:
        """
        Validate a value.

        Args:
            value: The value to validate

        Returns:
            ValidationResult indicating success/failure
        """
        pass


class RequiredValidator(BaseValidator):
    """Validates that a field is not empty."""

    def validate(self, value) -> ValidationResult:
        """Check if value is non-empty."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return ValidationResult(
                valid=False,
                error=self.tr("validation.required")
            )
        return ValidationResult(valid=True)


class EmailValidator(BaseValidator):
    """Validates email address format."""

    # RFC 5322 simplified regex pattern
    EMAIL_PATTERN = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )

    def validate(self, value) -> ValidationResult:
        """Check if value is a valid email address."""
        if not value:
            # Empty is valid (use RequiredValidator if you want to enforce)
            return ValidationResult(valid=True)

        if not isinstance(value, str):
            return ValidationResult(
                valid=False,
                error=self.tr("validation.email.invalid")
            )

        if not self.EMAIL_PATTERN.match(value.strip()):
            return ValidationResult(
                valid=False,
                error=self.tr("validation.email.invalid")
            )

        return ValidationResult(valid=True)


class URLValidator(BaseValidator):
    """Validates URL format (http/https)."""

    # URL pattern - requires http:// or https://
    URL_PATTERN = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$',  # path
        re.IGNORECASE
    )

    def validate(self, value) -> ValidationResult:
        """Check if value is a valid URL."""
        if not value:
            # Empty is valid (use RequiredValidator if you want to enforce)
            return ValidationResult(valid=True)

        if not isinstance(value, str):
            return ValidationResult(
                valid=False,
                error=self.tr("validation.url.invalid")
            )

        if not self.URL_PATTERN.match(value.strip()):
            return ValidationResult(
                valid=False,
                error=self.tr("validation.url.invalid")
            )

        return ValidationResult(valid=True)


class PasswordStrengthValidator(BaseValidator):
    """Validates password strength with configurable requirements."""

    def __init__(
        self,
        tr_func: Optional[Callable] = None,
        min_length: int = 8,
        require_uppercase: bool = False,
        require_lowercase: bool = False,
        require_digit: bool = False,
        require_special: bool = False
    ):
        """
        Initialize password validator with requirements.

        Args:
            tr_func: Translation function
            min_length: Minimum password length
            require_uppercase: Require at least one uppercase letter
            require_lowercase: Require at least one lowercase letter
            require_digit: Require at least one digit
            require_special: Require at least one special character
        """
        super().__init__(tr_func)
        self.min_length = min_length
        self.require_uppercase = require_uppercase
        self.require_lowercase = require_lowercase
        self.require_digit = require_digit
        self.require_special = require_special

    def validate(self, value) -> ValidationResult:
        """Check if password meets strength requirements."""
        if not value:
            # Empty is valid (use RequiredValidator if you want to enforce)
            return ValidationResult(valid=True)

        if not isinstance(value, str):
            return ValidationResult(valid=False, error=self.tr("validation.password.invalid"))

        # Check minimum length
        if len(value) < self.min_length:
            return ValidationResult(
                valid=False,
                error=self.tr("validation.password.too_short", min=self.min_length)
            )

        # Check uppercase requirement
        if self.require_uppercase and not re.search(r'[A-Z]', value):
            return ValidationResult(
                valid=False,
                error=self.tr("validation.password.need_uppercase")
            )

        # Check lowercase requirement
        if self.require_lowercase and not re.search(r'[a-z]', value):
            return ValidationResult(
                valid=False,
                error=self.tr("validation.password.need_lowercase")
            )

        # Check digit requirement
        if self.require_digit and not re.search(r'\d', value):
            return ValidationResult(
                valid=False,
                error=self.tr("validation.password.need_digit")
            )

        # Check special character requirement
        if self.require_special and not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
            return ValidationResult(
                valid=False,
                error=self.tr("validation.password.need_special")
            )

        # All requirements met - check if we should warn about weak password
        warnings = []
        if not self.require_uppercase and not re.search(r'[A-Z]', value):
            warnings.append("uppercase")
        if not self.require_digit and not re.search(r'\d', value):
            warnings.append("digit")
        if not self.require_special and not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
            warnings.append("special")

        if warnings:
            return ValidationResult(
                valid=True,
                warning=self.tr("validation.password.weak")
            )

        return ValidationResult(valid=True)


class LengthValidator(BaseValidator):
    """Validates string length constraints."""

    def __init__(
        self,
        tr_func: Optional[Callable] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None
    ):
        """
        Initialize length validator.

        Args:
            tr_func: Translation function
            min_length: Minimum length (None = no minimum)
            max_length: Maximum length (None = no maximum)
        """
        super().__init__(tr_func)
        self.min_length = min_length
        self.max_length = max_length

    def validate(self, value) -> ValidationResult:
        """Check if value meets length constraints."""
        if not value:
            # Empty is valid (use RequiredValidator if you want to enforce)
            return ValidationResult(valid=True)

        if not isinstance(value, str):
            value = str(value)

        length = len(value)

        if self.min_length is not None and length < self.min_length:
            return ValidationResult(
                valid=False,
                error=self.tr("validation.length.too_short", min=self.min_length)
            )

        if self.max_length is not None and length > self.max_length:
            return ValidationResult(
                valid=False,
                error=self.tr("validation.length.too_long", max=self.max_length)
            )

        return ValidationResult(valid=True)


class RegexValidator(BaseValidator):
    """Validates value against a regular expression pattern."""

    def __init__(
        self,
        pattern: str,
        tr_func: Optional[Callable] = None,
        error_message: str = "validation.regex.invalid"
    ):
        """
        Initialize regex validator.

        Args:
            pattern: Regular expression pattern
            tr_func: Translation function
            error_message: Translation key for error message
        """
        super().__init__(tr_func)
        self.pattern = re.compile(pattern)
        self.error_message = error_message

    def validate(self, value) -> ValidationResult:
        """Check if value matches the pattern."""
        if not value:
            # Empty is valid (use RequiredValidator if you want to enforce)
            return ValidationResult(valid=True)

        if not isinstance(value, str):
            value = str(value)

        if not self.pattern.match(value):
            return ValidationResult(
                valid=False,
                error=self.tr(self.error_message)
            )

        return ValidationResult(valid=True)
