import time
from datetime import datetime, timezone
import httpx
from pydantic import BaseModel, Field, ValidationError
from geointel.domain.schemas import Confidence, NormalizedEvidence

class UCDPError(RuntimeError): pass
class UCDPRawRecord(BaseModel):
    id: int | str
    country: str
    date_start: datetime | None = None
    date_end: datetime | None = None
    type_of_violence: int | None = None
    deaths_best: int | None = Field(default=None, ge=0)
    source_article: str | None = None

class UCDPConnector:
    """Adapter for a configured UCDP-compatible endpoint; endpoint path is never guessed."""
    def __init__(self, base_url: str, api_version: str, endpoint_path: str | None = None,
                 access_token: str | None = None, timeout: float = 10, retries: int = 2,
                 client: httpx.Client | None = None):
        self.base_url, self.api_version, self.endpoint_path = base_url.rstrip('/'), api_version, endpoint_path
        self.access_token, self.timeout, self.retries = access_token, timeout, retries
        self.client = client or httpx.Client(timeout=timeout)
    def collect(self, location: str) -> list[NormalizedEvidence]:
        if not self.endpoint_path:
            raise UCDPError("UCDP endpoint path is not configured; consult current UCDP API documentation")
        headers = {"Authorization": f"Bearer {self.access_token}"} if self.access_token else {}
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.client.get(f"{self.base_url}/{self.endpoint_path.lstrip('/')}",
                    params={"country": location, "version": self.api_version}, headers=headers, timeout=self.timeout)
                response.raise_for_status()
                payload = response.json()
                records = payload.get("Result", payload.get("results", payload)) if isinstance(payload, dict) else payload
                return [self.normalize(item, location) for item in records]
            except (httpx.HTTPError, ValueError, ValidationError, TypeError) as exc:
                last = exc
                if attempt < self.retries: time.sleep(0.05 * (2 ** attempt))
        raise UCDPError(f"UCDP retrieval failed after {self.retries + 1} attempts: {last}") from last
    def normalize(self, raw: dict, location: str) -> NormalizedEvidence:
        record = UCDPRawRecord.model_validate(raw)
        return NormalizedEvidence(source_name="UCDP", source_record_id=str(record.id),
            title=f"UCDP conflict record {record.id}",
            summary=f"UCDP coded violence record for {record.country}; best deaths: {record.deaths_best if record.deaths_best is not None else 'unknown'}.",
            published_at=None, event_date=record.date_start, retrieved_at=datetime.now(timezone.utc),
            geographic_scope=location, reliability=Confidence.HIGH,
            provenance={"provider":"UCDP", "dataset_version":self.api_version,
                        "type_of_violence":record.type_of_violence, "source_article":record.source_article})
