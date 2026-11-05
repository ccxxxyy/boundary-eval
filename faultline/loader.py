"""Loading task definitions and candidate solutions.

A solution is re-instantiated from scratch for every attempt. That matters:
the process is supposed to have died, so anything a solution stashed in a
module-level variable must be gone. Importing once and reusing the module
would let in-memory bookkeeping survive a crash and quietly turn an unsafe
solution into a passing one.
"""

from __future__ import annotations

import importlib.util
import sys
import types
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SolutionSource:
    """Compiled solution code that can be instantiated fresh per attempt."""

    def __init__(self, source: str, origin: str) -> None:
        self.origin = origin
        self.source = source
        self._code = compile(source, origin, "exec")

    @classmethod
    def from_path(cls, path: str | Path) -> "SolutionSource":
        path = Path(path)
        return cls(path.read_text(encoding="utf-8"), str(path))

    def instantiate(self) -> types.ModuleType:
        module = types.ModuleType(f"faultline_solution_{uuid.uuid4().hex}")
        module.__file__ = self.origin
        exec(self._code, module.__dict__)  # noqa: S102 - running candidate code is the point
        return module


@dataclass
class TaskBundle:
    task_id: str
    directory: Path
    module: Any

    @property
    def prompt(self) -> str:
        return (self.directory / "prompt.md").read_text(encoding="utf-8")

    @property
    def stub(self) -> str:
        return (self.directory / "stub.py").read_text(encoding="utf-8")

    @property
    def happy_path_test(self) -> str:
        return (self.directory / "happy_path_test.py").read_text(encoding="utf-8")

    def reference(self) -> SolutionSource:
        return SolutionSource.from_path(self.directory / "reference.py")

    def alternates(self) -> list[SolutionSource]:
        """Additional known-correct solutions, used to prove the grader does
        not merely accept one particular implementation shape."""
        directory = self.directory / "alternates"
        if not directory.is_dir():
            return []
        return [SolutionSource.from_path(p) for p in sorted(directory.glob("*.py"))]

    def broken(self) -> list[SolutionSource]:
        directory = self.directory / "broken"
        if not directory.is_dir():
            return []
        return [SolutionSource.from_path(p) for p in sorted(directory.glob("*.py"))]


def load_task(directory: str | Path) -> TaskBundle:
    directory = Path(directory)
    spec = importlib.util.spec_from_file_location(
        f"faultline_task_{directory.name}", directory / "task.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load task definition from {directory}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return TaskBundle(task_id=module.TASK_ID, directory=directory, module=module)


TASKS_ROOT = Path(__file__).resolve().parent.parent / "tasks"


def discover_tasks() -> list[TaskBundle]:
    return [
        load_task(p)
        for p in sorted(TASKS_ROOT.iterdir())
        if p.is_dir() and (p / "task.py").exists()
    ]
