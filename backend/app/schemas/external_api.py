"""Provider-neutral validation and responses for external API data.

No real provider fields are known yet. Replace ``ExternalPayload`` with explicit
field definitions once the provider's response contract has been selected.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, JsonValue, RootModel


class ExternalPayload(RootModel[dict[str, JsonValue]]):
    """A JSON object with no invented provider-specific fields."""


class ExternalSnapshotResponse(BaseModel):
    """A validated external API value stored by the local backend."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    received_at: datetime
    data: dict[str, JsonValue]
