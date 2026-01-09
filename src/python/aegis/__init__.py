# Project Aegis - Python Package
"""
Aegis compliance engine Python components.

This package contains:
- AI Bridge: ZeroMQ receiver for ML inference
- Digital Analyst: Behavioural risk scoring with XAI
- Consortium Node: ZKP broadcasting to consortium peers
- Secrets Provider: HSM/Vault abstraction layer
"""

__version__ = "1.0.0"
__author__ = "NUXA Ltd"

from aegis.digital_analyst import DigitalAnalyst
from aegis.secrets_provider import get_secrets_provider

__all__ = [
    "DigitalAnalyst",
    "get_secrets_provider",
]
