"""Optional Google emulator detection for the ``local`` profile (opt-in, never required).

The local registry adapter can route to the official **Firestore emulator** for
higher-fidelity local development WHEN the standard ``FIRESTORE_EMULATOR_HOST`` env var is
set AND the matching client library (from the ``[gcp]`` extra) imports. Otherwise it uses
its SDK-free SQLite path, which is the default.

This module only *detects* the opt-in; it deliberately performs **no google-cloud import at
module top level**. The adapter imports the google client lazily, inside ``__init__`` /
methods, and only on the emulator branch, so the default local path and the offline test
suite never import a google-cloud package.

There is no emulator for AlloyDB, so the SQLite path is the only SDK-free option for the
managed-store stand-in; the AlloyDB-backed catalog stays on the ``gcp`` profile.
"""

from __future__ import annotations

from hex_service_kit.netdefaults import ConfiguredEmptyError, read_env_setting

#: Standard Firestore emulator host env var.
FIRESTORE_EMULATOR_ENV = "FIRESTORE_EMULATOR_HOST"


def firestore_emulator_host() -> str | None:
    """Return the configured host, fall back when absent, and refuse an empty opt-in."""
    setting = read_env_setting(FIRESTORE_EMULATOR_ENV)
    if setting.is_unset:
        return None
    if setting.is_configured_empty:
        raise ConfiguredEmptyError(
            f"{FIRESTORE_EMULATOR_ENV} is set to an empty value; unset it for the "
            "SDK-free local fallback or configure an emulator host"
        )
    return setting.value


def firestore_client_available() -> bool:
    """Whether ``google-cloud-firestore`` is importable (the ``[gcp]`` extra is installed).

    The import is attempted lazily here (not at module top level) so that the default
    SDK-free local path never imports a google-cloud package.
    """
    try:
        import google.cloud.firestore  # noqa: F401  (lazy availability probe only)
    except Exception:  # noqa: BLE001 - any import failure means the emulator path is off
        return False
    return True


def firestore_emulator_active() -> bool:
    """True only when both the emulator env var is set AND the client lib imports."""
    return firestore_emulator_host() is not None and firestore_client_available()
