from typing import Protocol

from geointel.domain.schemas import (
    NormalizedEvidence,
    NormalizedForecastSignal,
    NormalizedNewsReport,
    NormalizedOperationalEvent,
)

NormalizedRecord = (
    NormalizedEvidence
    | NormalizedForecastSignal
    | NormalizedOperationalEvent
    | NormalizedNewsReport
)


class EvidenceConnector(Protocol):
    connector_name: str

    def collect(self, location: str, horizon_months: int) -> list[NormalizedRecord]: ...


class DisabledConnector:
    def __init__(self, connector_name: str):
        self.connector_name = connector_name

    def collect(self, location: str, horizon_months: int) -> list[NormalizedRecord]:
        return []
