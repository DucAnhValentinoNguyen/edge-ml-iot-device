"""Protocol adapter and onboarding primitives for the edge gateway."""

from .adapter import GatewayAdapter, IngressResult, RawTelegram
from .profiles import ProfileRegistry

__all__ = ["GatewayAdapter", "IngressResult", "ProfileRegistry", "RawTelegram"]

