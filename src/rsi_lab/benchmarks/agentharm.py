"""Capability boundary for the optional AgentHarm benchmark.

The former Inspect bridge replaced candidate execution with an instruction
projection. Executable Harnesses require a native tool/effect bridge that runs
the selected resource version. Until that bridge is implemented and validated,
planning rejects AgentHarm before any model call or partial experiment starts.
Historical runs keep their original adapter in their frozen source archive.
"""
from rsi_lab.errors import UnsupportedCapability

_REASON = (
    "AgentHarm does not yet support executable Harness versions. Its former "
    "Inspect instruction projection has been removed; choose a supported task "
    "backend or implement the native Harness/tool bridge before enabling AgentHarm."
)


def preflight(spec):
    raise UnsupportedCapability(_REASON)


def evaluate(program, directory, config, common, *, provider_factory=None):
    raise UnsupportedCapability(_REASON)
