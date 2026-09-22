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
    upstream_dependencies: tuple[str, ...] = ()

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        value["integration_mode"] = self.integration_mode.value
        value["documentation_status"] = self.documentation_status.value
        return value


DOCS = {
    "UCDP": ("https://ucdp.uu.se/apidocs/", "https://ucdp.uu.se/downloads/"),
    "ACLED": (
        "https://acleddata.com/acleddatanew/wp-content/uploads/dlm_uploads/2023/06/ACLED-API-Documentation.pdf",
    ),
    "VIEWS": ("https://viewsforecasting.org/",),
    "CAST": (
        "https://www.giga-hamburg.de/en/research-and-transfer/projects/cast-conflict-forecasting",
    ),
}


def capabilities(settings: Settings | None = None) -> list[ProviderCapability]:
    settings = settings or Settings()
    rows = []
    definitions = {
        "UCDP": (
            settings.ucdp_enabled,
            settings.ucdp_base_url,
            settings.ucdp_endpoint_path,
            "observed_historical",
            "geointel-ucdp-adapter-v1",
            True,
        ),
        "ACLED": (
            settings.acled_enabled,
            settings.acled_base_url,
            settings.acled_endpoint_path,
            "observed_reported_event",
            "geointel-acled-adapter-v1",
            None,
        ),
        "VIEWS": (
            settings.views_enabled,
            settings.views_base_url,
            settings.views_endpoint_path,
            "predictive_model_output",
            "geointel-views-adapter-v1",
            None,
        ),
        "CAST": (
            settings.cast_enabled,
            settings.cast_base_url,
            settings.cast_endpoint_path,
            "predictive_model_output",
            "geointel-cast-adapter-v1",
            None,
        ),
    }
    for name, (enabled, base, path, role, schema, auth) in definitions.items():
        configured = bool(base and path)
        mode = (
            IntegrationMode.OPERATOR_ADAPTER if enabled and configured else IntegrationMode.DISABLED
        )
        rows.append(
            ProviderCapability(
                provider=name,
                connector_version="0.1.1",
                integration_mode=mode,
                documentation_status=DocumentationStatus.OPERATOR_ADAPTER_REQUIRED,
                official_documentation=DOCS[name],
                documentation_accessed=(
                    "2026-09-22 (network access returned 401; contracts not verified)"
                ),
                authentication_required=auth,
                configured=configured,
                enabled=enabled,
                epistemic_role=role,
                geography_levels=(),
                temporal_resolution=(),
                pagination="adapter cursor contract only; no upstream contract claimed",
                rate_limit="unknown; conservative bounded retries",
                maximum_safe_page_size=None,
                schema_version=schema,
                health_status="unknown" if enabled else "disabled",
                health_message=(
                    "configured operator adapter; not checked" if enabled else "disabled by default"
                )[:300],
            )
        )
    return rows


def public_capabilities(settings: Settings | None = None) -> list[dict[str, Any]]:
    return [item.public() for item in capabilities(settings)]
