"""Errors surfaced at CLI and adapter boundaries."""


class LabError(Exception):
    """Expected, actionable lab error."""


class ValidationError(LabError, ValueError):
    """An input violates its declared schema."""


class ModelResponseValidationError(ValidationError):
    """A confirmed model response violates the declared output contract."""


class IntegrityError(LabError):
    """Stored bytes or references no longer match their manifest."""


class ConflictError(LabError):
    """An identity was reused with different content or state is stale."""


class UnsupportedCapability(LabError):
    """A protocol cannot run on the declared backend."""


class BudgetExceeded(LabError):
    """Available budget cannot cover a request; optional numeric evidence is safe to log."""
    def __init__(self, message, *, resource=None, required=None, limit=None):
        super().__init__(message)
        self.details = ({"resource": resource, "required": required, "limit": limit}
                        if resource is not None else None)


class PermissionDenied(LabError):
    """A capability does not authorize this operation."""



class OutcomeUnknown(LabError):
    """Execution cannot safely be retried under the same operation identity."""
