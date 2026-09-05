"""Controlled errors exposed by the semantic service."""


class SlangMcpError(Exception):
    """Base class for expected user-facing failures."""


class ProjectNotLoadedError(SlangMcpError):
    """Raised when a query requires an active project."""


class UnknownLogicalModuleError(SlangMcpError):
    """Raised when a provider cannot resolve a logical module."""


class InvalidProjectConfigError(SlangMcpError):
    """Raised when resolved build inputs are invalid."""


class CompilationError(SlangMcpError):
    """Raised when Slang cannot construct a compilation."""


class SymbolNotFoundError(SlangMcpError):
    """Raised when a symbol identifier cannot be found."""


class AmbiguousSymbolError(SlangMcpError):
    """Raised when a symbol name does not identify one declaration."""


class InstanceNotFoundError(SlangMcpError):
    """Raised when an elaborated instance path cannot be found."""


class InvalidTopError(SlangMcpError):
    """Raised when a requested hierarchy root is not a top instance."""


class SignatureUnavailableError(SlangMcpError):
    """A declaration cannot be independently elaborated with default parameters."""
