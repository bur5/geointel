from typing import Protocol
from geointel.domain.schemas import NormalizedEvidence
class EvidenceConnector(Protocol):
    def collect(self, location: str) -> list[NormalizedEvidence]: ...
