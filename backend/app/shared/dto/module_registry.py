from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleRegistryEntry:
    """Simple registry entry describing a module."""

    name: str
    status: str = "ready"
