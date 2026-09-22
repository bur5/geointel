from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from geointel.config import Settings
from geointel.providers.runtime import DocumentationStatus, IntegrationMode


@dataclass(frozen=True)
class ProviderCapability:
    provider: str
    connector_version: str
    integration_mode: IntegrationMode
    documentation_status: DocumentationStatus
    official_documentation: tuple[str, ...]
    documentation_accessed: str
    authentication_required: bool | None
    authentication_configured: bool
    configured: bool
    enabled: bool
    epistemic_role: str
    geography_levels: tuple[str, ...]
    temporal_resolution: tuple[str, ...]
    pagination: str
    rate_limit: str
    maximum_safe_page_size: int | None
    schema_version: str
    health_status: str
    health_message: str
    last_collection_status: str = "not_checked"
    upstream_dependencies: tuple[str, ...] = ()

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        value["integration_mode"] = self.integration_mode.value
        value["documentation_status"] = self.documentation_status.value
        return value


DOCS = {
    "UCDP": ("https://ucdp.uu.se/apidocs/",),
    "ACLED": (
        "https://acleddata.com/acled-api-documentation",
        "https://acleddata.com/api-documentation/acled-endpoint",
        "https://acleddata.com/api-documentation/elements-acleds-api",
    ),
    "CAST": ("https://acleddata.com/api-documentation/cast-endpoint",),
    "VIEWS": (
        "https://viewsforecasting.org/data",
        "https://viewsforecasting.org/source-code/",
        "https://viewsforecasting.org/user-guide/",
    ),
}


def _mode(enabled: bool, configured: bool, requested: str) -> IntegrationMode:
    value = requested.casefold()
    if value == "official_api":
        return IntegrationMode.OFFICIAL_API
    if value == "fixture":
        return IntegrationMode.FIXTURE
    if value == "operator_adapter" or (enabled and configured):
        return IntegrationMode.OPERATOR_ADAPTER
    return IntegrationMode.DISABLED


def capabilities(settings: Settings | None = None) -> list[ProviderCapability]:
    settings = settings or Settings()
    shared_auth = bool(settings.acled_username and settings.acled_password)
    definitions = {
        "UCDP": dict(
            enabled=settings.ucdp_enabled,
            configured=bool(settings.ucdp_access_token)
            if settings.ucdp_mode.casefold() == "official_api"
            else bool(settings.ucdp_endpoint_path),
            requested=settings.ucdp_mode,
            auth=bool(settings.ucdp_access_token),
            role="observed_historical",
            status=DocumentationStatus.VERIFIED,
            schema="ucdp-gedevents-official-v1",
            geo=("country", "event_coordinates"),
            temporal=("event",),
            pagination="pagesize/page bounded by TotalPages",
            rate="5,000 requests/day (provider quota)",
            page=1000,
            deps=(),
        ),
        "ACLED": dict(
            enabled=settings.acled_enabled,
            configured=shared_auth
            if settings.acled_mode.casefold() == "official_api"
            else bool(settings.acled_endpoint_path),
            requested=settings.acled_mode,
            auth=shared_auth,
            role="observed_reported_event",
            status=DocumentationStatus.VERIFIED,
            schema="acled-events-official-v1",
            geo=("country", "admin1", "admin2", "admin3", "coordinates"),
            temporal=("event",),
            pagination="cursor (0, next_cursor, null termination); page mode not used",
            rate="provider/account policy",
            page=5000,
            deps=(),
        ),
        "CAST": dict(
            enabled=settings.cast_enabled,
            configured=shared_auth
            if settings.cast_mode.casefold() == "official_api"
            else bool(settings.cast_endpoint_path),
            requested=settings.cast_mode,
            auth=shared_auth,
            role="predictive_event_counts",
            status=DocumentationStatus.VERIFIED,
            schema="acled-cast-official-v1",
            geo=("country", "admin1"),
            temporal=("monthly",),
            pagination="bounded cursor when supplied by API",
            rate="provider/account policy",
            page=None,
            deps=("ACLED OAuth",),
        ),
        "VIEWS": dict(
            enabled=settings.views_enabled,
            configured=bool(settings.views_base_url and settings.views_endpoint_path),
            requested="operator_adapter" if settings.views_enabled else "disabled",
            auth=False,
            role="predictive_model_output",
            status=DocumentationStatus.OPERATOR_ADAPTER_REQUIRED,
            schema="geointel-views-adapter-v1",
            geo=(),
            temporal=(),
            pagination="exact current official technical contract not independently verified",
            rate="unknown",
            page=None,
            deps=(),
        ),
    }
    rows = []
    for name, item in definitions.items():
        mode = _mode(item["enabled"], item["configured"], item["requested"])
        rows.append(
            ProviderCapability(
                provider=name,
                connector_version="0.1.2",
                integration_mode=mode,
                documentation_status=item["status"],
                official_documentation=DOCS[name],
                documentation_accessed="2026-09-22",
                authentication_required=None if name == "VIEWS" else True,
                authentication_configured=item["auth"],
                configured=item["configured"],
                enabled=item["enabled"],
                epistemic_role=item["role"],
                geography_levels=item["geo"],
                temporal_resolution=item["temporal"],
                pagination=item["pagination"],
                rate_limit=item["rate"],
                maximum_safe_page_size=item["page"],
                schema_version=item["schema"],
                health_status="unknown" if item["enabled"] else "disabled",
                health_message="not checked; use explicit check-live"
                if item["enabled"]
                else "disabled by default",
                upstream_dependencies=item["deps"],
            )
        )
    return rows


def public_capabilities(settings: Settings | None = None) -> list[dict[str, Any]]:
    return [item.public() for item in capabilities(settings)]
