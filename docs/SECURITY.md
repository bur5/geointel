# Security

Secrets belong in environment variables and are excluded from stored provider configuration, logs and version control. `.env.example` contains names only. Before internet exposure add authentication, authorization, rate limiting, request-size controls and audit logs. Treat retrieved content as hostile data: constrain lengths, prevent prompt injection from granting tools, validate structured outputs, and never execute source text. Database roles should use least privilege; production credentials must differ from Compose defaults. Backups and deletion need explicit controls.

Developer automation permission model: Level 0 read/analyze/propose; Level 1 isolated branch/sandbox writes and tests; Level 2 merge/deploy only after explicit APPROVE. Database deletion, auth, secrets and production infrastructure require extra restrictions. Intended flow: text/voice → interface → developer agent → branch/sandbox → changes → tests/security checks → preview → explicit approve/reject → merge/deploy. Voice is future interface-only functionality and receives no privileged forecasting role.

VIEWS and UCDP payloads are untrusted data only: connector records are length/schema
constrained, are never executed, and grant no tools or code-writing authority. Connector errors
stored in collection metadata are bounded; endpoint credentials must never be embedded in URLs.

Do not deploy v0.0.2 as-is. Report vulnerabilities privately to repository maintainers without
including live credentials or personal data.
