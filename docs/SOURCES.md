# Source and connector policy

A Source identifies a provider; Evidence is the retrieved artifact plus retrieval/publication/event dates, geography, reliability and provenance. Evidence never becomes a confirmed Event merely because it was published. Connector failures are bounded, logged and exposed to analysis context rather than crashing the full collection process.

UCDP is the initial adapter. Base URL/version, timeout, retries and authorization are configurable; raw records are validated and normalized. Because API behavior can change, v0.0.1 refuses to invent an endpoint. Confirm current UCDP documentation and licensing before supplying an endpoint.

Planned adapters include ACLED, CAST, VIEWS, SIPRI, World Bank, IMF, OECD, Eurostat, UN WPP/UNHCR/IOM DTM/UN DESA, WGI, V-Dem, Freedom House, UNODC, GTD, GDELT, governments, ministries, embassies, aviation/border authorities and licensed Reuters/AP/AFP access. Each must honor terms, robots/access controls and licensing; never circumvent restrictions. Independent confirmation and per-source reliability are future priorities.
