"""Read-only, point-in-time briefing generation from persisted GEOINTEL records."""

from .service import Briefing, BriefingRequest, BriefingType, NarrativeProvider, generate_briefing

__all__ = ["Briefing", "BriefingRequest", "BriefingType", "NarrativeProvider", "generate_briefing"]
