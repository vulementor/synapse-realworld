from __future__ import annotations

from typing import Protocol

from synapse_realworld.domain.models import Household


class PopulationGenerator(Protocol):
    @property
    def population_version(self) -> str: ...

    def generate(self, size: int, *, seed: int) -> list[Household]: ...
