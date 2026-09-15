from __future__ import annotations


class ConnPilotError(Exception):
    """Base error for expected engine failures."""


class CatalogError(ConnPilotError):
    pass


class ProjectValidationError(ConnPilotError):
    def __init__(self, issues: list[str]):
        super().__init__("Project validation failed")
        self.issues = issues


class ExecutionError(ConnPilotError):
    pass

