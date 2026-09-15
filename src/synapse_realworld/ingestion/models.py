from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class IngestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    received: int = Field(ge=0)
    inserted: int = Field(ge=0)
    duplicates: int = Field(ge=0)
    snapshot_recorded: bool = False

    @property
    def accepted_ratio(self) -> float:
        if self.received == 0:
            return 1.0
        return self.inserted / self.received
