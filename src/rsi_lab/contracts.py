"""Versioned boundary records. Type hints are checked at construction and decoding.

Content identities never convey authority. Candidate provenance is a separate
record, and bindings are never embedded into the snapshot they reference.
"""

from __future__ import annotations

import re
import types
from dataclasses import MISSING, fields
from enum import Enum
from typing import Union, get_args, get_origin, get_type_hints

from .errors import ValidationError
from .serialization import primitive


def _convert(value, expected, path: str, decoding: bool):
    origin, args = get_origin(expected), get_args(expected)
    if origin in (Union, types.UnionType):
        for alternative in args:
            try:
                return _convert(value, alternative, path, decoding)
            except ValidationError:
                continue
        raise ValidationError(f"{path}: does not match {expected}")
    if expected is type(None):
        if value is not None:
            raise ValidationError(f"{path}: expected null")
        return None
    if origin is tuple:
        if type(value) not in ((list, tuple) if decoding else (tuple,)):
            raise ValidationError(f"{path}: expected ordered array")
        if len(args) != 2 or args[1] is not Ellipsis:
            raise ValidationError(f"{path}: unsupported tuple schema")
        return tuple(_convert(v, args[0], f"{path}[{i}]", decoding) for i, v in enumerate(value))
    if isinstance(expected, type) and issubclass(expected, StrictRecord):
        if decoding and type(value) is dict:
            return expected.from_dict(value)
        if type(value) is not expected:
            raise ValidationError(f"{path}: expected {expected.__name__}")
        return value
    if isinstance(expected, type) and issubclass(expected, Enum):
        if type(value) is expected:
            return value
        if decoding and type(value) is str:
            try:
                return expected(value)
            except ValueError:
                pass
        raise ValidationError(f"{path}: unknown {expected.__name__}: {value!r}")
    if type(value) is not expected:
        raise ValidationError(f"{path}: expected {expected.__name__}, got {type(value).__name__}")
    return value


class StrictRecord:
    def __post_init__(self):
        hints = get_type_hints(type(self))
        for field in fields(self):
            _convert(getattr(self, field.name), hints[field.name], field.name, False)
        if hasattr(self, "schema_version") and self.schema_version != 1:
            raise ValidationError(f"Unsupported schema_version: {self.schema_version}")
        self.validate()

    def validate(self):
        """Subclasses add semantic checks after recursive field type checking."""

    def to_dict(self) -> dict:
        return primitive(self)

    @classmethod
    def from_dict(cls, value: dict):
        if type(value) is not dict:
            raise ValidationError(f"{cls.__name__}: expected object")
        spec = {f.name: f for f in fields(cls)}
        extra = set(value) - set(spec)
        required = {f.name for f in spec.values() if f.default is MISSING and f.default_factory is MISSING}
        if "schema_version" in spec:
            required.add("schema_version")
        if extra or required - set(value):
            raise ValidationError(f"{cls.__name__}: unknown={sorted(extra)}, missing={sorted(required - set(value))}")
        hints = get_type_hints(cls)
        return cls(**{k: _convert(v, hints[k], f"{cls.__name__}.{k}", True) for k, v in value.items()})


def require_id(value: str, name: str = "id"):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}", value):
        raise ValidationError(f"{name}: invalid identity {value!r}")


def require_count(value: int, name: str, minimum: int = 0):
    if type(value) is not int or value < minimum:
        raise ValidationError(f"{name}: must be an integer >= {minimum}")


def require_sha(value: str):
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValidationError("Expected lowercase SHA-256 identity")


class CandidateOrigin(str, Enum):
    CONTROL = "control"
    STRESS = "stress"
    NATURAL = "natural"


class CursorFamily(str, Enum):
    PUBLIC_DEVELOPMENT = "public_development"
    ADMISSION_PROBE = "admission_probe"
    INDEPENDENT_EVALUATION = "independent_evaluation"


class Partition(str, Enum):
    TRAIN = "train"
    DEV = "dev"
    CALIBRATION = "calibration"
    SEALED = "sealed"
