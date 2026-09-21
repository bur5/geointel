from geointel.connectors.views import VIEWSConnector, VIEWSError
from geointel.domain.schemas import NormalizedForecastSignal


class CASTError(VIEWSError):
    pass


class CASTConnector(VIEWSConnector):
    """Predictive CAST adapter. It shares reliability mechanics, not VIEWS semantics."""

    connector_name = "CAST"

    def collect(self, location: str, horizon_months: int = 12) -> list[NormalizedForecastSignal]:
        if not self.endpoint_path:
            raise CASTError("CAST verified adapter endpoint is not configured")
        try:
            return super().collect(location, horizon_months)
        except VIEWSError as exc:
            raise CASTError(str(exc).replace("VIEWS", "CAST")) from exc

    def normalize(
        self,
        raw: dict,
        requested_location: str,
        requested_horizon_months: int,
        retrieval_url: str | None = None,
    ) -> NormalizedForecastSignal:
        signal = super().normalize(raw, requested_location, requested_horizon_months, retrieval_url)
        signal.provider = "CAST"
        signal.provenance.update(
            provider="CAST", schema="geointel-cast-adapter-v1", predictive_not_observed=True
        )
        return signal
