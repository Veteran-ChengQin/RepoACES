"""RepoACES MultiAgent prototype.

This package keeps the first RepoACES implementation untouched and adds a
workflow-oriented variant where each development phase is handled by a separate
OpenHands-backed agent.
"""

__all__ = [
    "MultiAgentRepoACESOrchestrator",
]

from .orchestrator import MultiAgentRepoACESOrchestrator
