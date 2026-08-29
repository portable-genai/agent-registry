"""``python -m agent_registry`` — run the API with uvicorn.

Reads ``API_HOST`` and ``PORT`` (default 8083). The bind default is fail-closed via the
shared ``hex-service-kit`` commons: the no-auth ``local`` profile binds
loopback unless ``AGENT_REGISTRY_ALLOW_INSECURE_DEMO=1`` explicitly opts into exposure;
secure profiles keep the container-friendly ``0.0.0.0`` default (the deployed container
runs ``AGENT_REGISTRY_PROFILE=gcp``, fronted by the platform).

The bind guard reads ``bind_profile``, not a raw environment read with its own ``local``
default: this is the restriction half of the profile decision, so a run that never named a
profile must look like ``local`` here and stay on loopback. The S2S rule is the relaxation
half and points the other way.
"""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn
    from hex_service_kit import resolve_bind_host

    from agent_registry.config import resolve_profile

    host = resolve_bind_host(
        resolve_profile().bind_profile,
        host_env="API_HOST",
        insecure_demo_env="AGENT_REGISTRY_ALLOW_INSECURE_DEMO",
    )
    uvicorn.run(
        "agent_registry.api.app:app",
        host=host,
        port=int(os.environ.get("PORT", "8083")),
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
