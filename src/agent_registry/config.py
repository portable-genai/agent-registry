"""Runtime configuration.

A single :class:`Settings` object is loaded from ``config/settings.yaml`` with
``${ENV:-default}`` interpolation, then handed to every adapter constructor
(``def __init__(self, settings: Settings) -> None``). The ``profile`` selects which
adapter family the :class:`~agent_registry.container.Container` binds:

* ``gcp``    : AlloyDB / Firestore managed adapter (real, lazy SDK calls).
* ``local``  : a WORKING offline laptop adapter (SQLite catalog, no Google Cloud
  SDKs, no API key, no emulator required). What dev / test / CI name explicitly.
  Routes to the Firestore emulator only when ``FIRESTORE_EMULATOR_HOST`` is set and
  the client library imports.
* ``onprem`` : fail-fast Google Distributed Cloud migration placeholders.

The GCP region is configurable and defaults to ``asia-southeast1``. Residency is enforced in three
places from the same allowlist: ``terraform plan`` rejects a ``region`` outside
``allowed_regions`` (``infra/terraform/variables.tf``), Org Policy ``gcp.resourceLocations``
refuses resources elsewhere in the project (``infra/terraform/org_policy.tf``), and
:meth:`Settings.from_dict` refuses
to build a configuration whose region is outside ``allowed_regions`` here, so a mis-set
``GCP_REGION`` fails at process start rather than writing agent metadata into an
unapproved region.

The profile itself is resolved in THREE states, not two: :func:`resolve_profile` is the only
reader of ``AGENT_REGISTRY_PROFILE``, and it distinguishes unset (nobody chose), configured-empty
(a boot error), and ``local`` (someone chose the no-auth offline catalog). The distinction is load
bearing because ``local`` is exactly the profile the S2S rule grants an opening to, so
reading an absent variable as ``local`` turned a lost config map into a writable catalog. See
:class:`ProfileChoice` for why the two derived strings point opposite ways.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from hex_service_kit.netdefaults import EnvSetting, read_env_setting

from .envread import setting_or_default

REGION = "asia-southeast1"
DEFAULT_ALLOWED_REGIONS: tuple[str, ...] = (REGION,)

#: The one environment variable that names the profile. Only :func:`resolve_profile` may read
#: it; ``tests/test_profile_single_source.py`` fails the build if another module does.
_PROFILE_ENV = "AGENT_REGISTRY_PROFILE"

#: Every profile that binds an adapter family. The comparison against it is EXACT and
#: case-sensitive, so ``Local`` is a typo that refuses rather than a silent choice.
RUNTIME_PROFILES = frozenset({"gcp", "local", "onprem"})

#: The profile string handed to every posture RELAXATION when no profile was ever named. It is
#: deliberately NOT a member of :data:`RUNTIME_PROFILES` and never reaches a
#: :class:`~agent_registry.container.Container` binding: it exists so that "no choice was
#: made" is a distinct input to the security layers rather than being indistinguishable from a
#: chosen ``local``.
UNCONSENTED_PROFILE = "unconfigured"


class ResidencyError(ValueError):
    """Raised when the configured region is outside the residency allowlist."""


class ProfileError(ValueError):
    """Raised when a named profile is one nothing binds, including a capitalisation typo."""


def _validate_profile(profile: str) -> str:
    """Fail closed on a profile string nothing binds, INCLUDING a capitalisation typo.

    Every posture decision downstream matches the profile string exactly, so ``Local``
    selects none of the relaxations but also none of the restrictions. Normalising the case
    here would turn a typo into a silent choice; refusing it turns the typo into a load
    failure, which is what an operator can actually see and fix.
    """
    if profile not in RUNTIME_PROFILES:
        expected = ", ".join(sorted(RUNTIME_PROFILES))
        raise ProfileError(f"unknown {_PROFILE_ENV} {profile!r}; expected one of: {expected}")
    return profile


@dataclass(frozen=True, slots=True)
class ProfileChoice:
    """The ONE resolution of the profile, and what each consumer must key off.

    The two derived profile strings differ because the two decisions fail closed in OPPOSITE
    directions, so a single "effective profile" string would harden one and weaken the other.
    """

    #: Which adapter family to bind. Absent consent this is still ``local`` (the SDK-free
    #: SQLite catalog), because the alternative would import cloud SDKs that are not installed.
    profile: str = "local"
    #: Was the profile named DELIBERATELY (the env var, or a ``profile:`` value in the
    #: settings file, present and non-blank)?
    explicit: bool = True

    @property
    def exposure_profile(self) -> str:
        """The profile every *relaxation* keys off, where ``local`` is the PERMISSIVE case.

        The S2S rule grants something extra to ``local`` (an unset shared secret leaves the
        catalog routes open for loopback dev), so an unconsented run must NOT look like
        ``local``: it gets :data:`UNCONSENTED_PROFILE`, for which an unset secret is a refusal.
        """
        return self.profile if self.explicit else UNCONSENTED_PROFILE

    @property
    def bind_profile(self) -> str:
        """The profile the bind guard keys off, where ``local`` is the RESTRICTIVE case.

        ``resolve_bind_host`` confines ``local`` to loopback and lets fronted profiles take
        ``0.0.0.0``, so here an unconsented run must look like ``local`` and stay on loopback.
        """
        return self.profile if self.explicit else "local"

    @property
    def service_auth_configured(self) -> bool:
        """May S2S callers be authenticated at all, or is the decision unconfigured?"""
        return self.explicit


def resolve_profile(declared: str = "", environ: Mapping[str, str] | None = None) -> ProfileChoice:
    """Read the profile once: absent inherits confinement, empty refuses, and values validate.

    Three states, not two. ``AGENT_REGISTRY_PROFILE`` wins when it has a value, configured-empty
    refuses instead of inheriting a default, and an absent variable permits a non-blank
    ``profile:`` in the settings file to be the deliberate choice. When neither source names
    one, nobody chose, which is not the same input as choosing ``local``.

    A value that IS present is validated here rather than at first port access, so a typo is
    a load failure naming the variable instead of a service that has already picked its
    posture from a string nothing binds.
    """
    if environ is None:
        setting = read_env_setting(_PROFILE_ENV)
    else:
        raw = environ.get(_PROFILE_ENV)
        setting = EnvSetting(name=_PROFILE_ENV, raw=raw, value="" if raw is None else raw.strip())
    if setting.is_configured_empty:
        raise ProfileError(
            f"{_PROFILE_ENV} is set but empty; unset it to inherit the confined offline "
            f"adapters, or name one of {sorted(RUNTIME_PROFILES)}"
        )
    chosen = setting.value or (declared or "").strip()
    if chosen:
        _validate_profile(chosen)
        return ProfileChoice(profile=chosen, explicit=True)
    return ProfileChoice(profile="local", explicit=False)


def _as_region_tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    """Read an allowlist written either as a YAML list or as a comma-separated string."""
    if value is None:
        return default
    items = value if isinstance(value, list) else str(value).split(",")
    parsed = tuple(str(item).strip() for item in items if str(item).strip())
    return parsed or default


_DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"
_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def _interpolate(value: Any) -> Any:
    """Recursively expand ``${VAR:-default}`` placeholders, in THREE states rather than two.

    ``${VAR:-default}`` IS ``setting_or_default(VAR, default)`` written in YAML, so it delegates
    to that one implementation rather than re-stating the rule with a hand-written message:
    UNSET takes the written default, SET-AND-EMPTY raises
    :class:`~hex_service_kit.netdefaults.ConfiguredEmptyError`, SET-AND-VALID wins. Note the
    exception type: ``ConfiguredEmptyError`` is a ``RuntimeError``, not the ``ValueError`` this
    loader would raise.
    """
    if isinstance(value, str):

        def _sub(match: re.Match[str]) -> str:
            return setting_or_default(match.group(1), match.group(2) or "")

        return _ENV_PATTERN.sub(_sub, value)
    if isinstance(value, dict):
        return {k: _interpolate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v) for v in value]
    return value


@dataclass(frozen=True, slots=True)
class AlloyDBSettings:
    """Connection facts for the AlloyDB-backed catalog (gcp profile, alloydb backend)."""

    instance_uri: str = ""  # projects/.../locations/.../clusters/.../instances/...
    database: str = "agent_registry"
    user: str = "registry_app"
    ip_type: str = "PRIVATE"
    table: str = "agent_cards"


@dataclass(frozen=True, slots=True)
class FirestoreSettings:
    """Connection facts for the Firestore-backed catalog (gcp profile, firestore backend)."""

    database: str = "(default)"
    collection: str = "agent_cards"


@dataclass(frozen=True, slots=True)
class RegistrySettings:
    """Registry self-identity used to build A3's own ``/.well-known/agent-card.json``."""

    name: str = "agent-registry"
    public_url: str = f"https://agent-registry.{REGION}.run.app"
    version: str = "0.1.0"
    quality_url: str = ""
    observability_url: str = ""
    release_policy_version: str = ""
    release_dataset_id: str = ""
    release_dataset_version: str = ""
    release_dataset_digest: str = ""
    release_evaluator: str = ""
    release_threshold_policy_digest: str = ""
    release_artifact_prefixes: tuple[str, ...] = ()
    release_redteam_categories: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LocalSettings:
    """Path for the SDK-free ``local`` profile catalog store (SQLite).

    An empty string selects the per-package default under ``~/.agent_registry/``; tests
    pass ``:memory:`` for an ephemeral, deterministic store. No Google Cloud here. The
    optional Firestore-emulator branch is opted into separately via the standard
    ``FIRESTORE_EMULATOR_HOST`` env var (see :mod:`agent_registry.adapters.local._emulator`).
    """

    db_path: str = ""  # SQLite catalog; "" => ~/.agent_registry/local.db


@dataclass(frozen=True, slots=True)
class Settings:
    """Top-level configuration for the registry service."""

    project_id: str = "your-gcp-project"
    region: str = REGION
    # Residency allowlist. Mirrors the Terraform variable of the same name; the loader
    # refuses a region outside it (fail fast at process start, not at first write).
    allowed_regions: tuple[str, ...] = DEFAULT_ALLOWED_REGIONS
    profile: str = "local"  # gcp | local | onprem
    # Which managed store the gcp profile uses. Documentation/Terraform value only;
    # the actual adapter is chosen by the dotted binding under ``adapters:``.
    backend: str = "alloydb"  # alloydb | firestore
    kms_key: str = ""  # regional Cloud KMS key for CMEK (empty under local)
    registry: RegistrySettings = field(default_factory=RegistrySettings)
    alloydb: AlloyDBSettings = field(default_factory=AlloyDBSettings)
    firestore: FirestoreSettings = field(default_factory=FirestoreSettings)
    local: LocalSettings = field(default_factory=LocalSettings)
    adapters: dict[str, dict[str, str]] = field(default_factory=dict)
    # Was the profile chosen DELIBERATELY, or merely inherited because nothing named one?
    # ``from_dict`` sets this False when neither AGENT_REGISTRY_PROFILE nor a ``profile:`` value
    # in the settings file is present. Direct construction is deliberate by definition (a
    # caller named the profile in code), so the default is True. Every posture RELAXATION
    # reads :attr:`exposure_profile` rather than :attr:`profile`, so an unconsented run does
    # not inherit the loopback-dev openings that ``local`` is granted.
    profile_explicit: bool = True

    @property
    def exposure_profile(self) -> str:
        """The profile every posture RELAXATION keys off (see :class:`ProfileChoice`)."""
        return ProfileChoice(self.profile, self.profile_explicit).exposure_profile

    @property
    def bind_profile(self) -> str:
        """The profile the bind guard keys off (see :class:`ProfileChoice`)."""
        return ProfileChoice(self.profile, self.profile_explicit).bind_profile

    @classmethod
    def load(cls, path: str | os.PathLike[str] | None = None) -> Settings:
        cfg_path = Path(path) if path is not None else _DEFAULT_SETTINGS_PATH
        raw: dict[str, Any] = {}
        if cfg_path.exists():
            loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            raw = _interpolate(loaded)
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Settings:
        adb = raw.get("alloydb", {}) or {}
        fs = raw.get("firestore", {}) or {}
        reg = raw.get("registry", {}) or {}
        loc = raw.get("local", {}) or {}
        # The AGENT_REGISTRY_PROFILE env var wins over any value baked into ``raw`` so the
        # CLI / Makefile / CI can flip profiles without editing settings.yaml. Neither source
        # supplies a default: absent from both means nobody chose (see resolve_profile).
        choice = resolve_profile(str(raw.get("profile", "") or ""))
        region = str(raw.get("region", REGION))
        allowed_regions = _as_region_tuple(raw.get("allowed_regions"), DEFAULT_ALLOWED_REGIONS)
        if region not in allowed_regions:
            raise ResidencyError(
                f"region '{region}' is outside the residency allowlist "
                f"{list(allowed_regions)}; set allowed_regions (AGENT_REGISTRY_ALLOWED_REGIONS) "
                "to the approved regions before deploying there."
            )
        return cls(
            project_id=str(raw.get("project_id", "your-gcp-project")),
            region=region,
            allowed_regions=allowed_regions,
            profile=choice.profile,
            profile_explicit=choice.explicit,
            backend=str(raw.get("backend", "alloydb")),
            kms_key=str(raw.get("kms_key", "")),
            registry=RegistrySettings(
                name=str(reg.get("name", "agent-registry")),
                public_url=str(reg.get("public_url") or f"https://agent-registry.{region}.run.app"),
                version=str(reg.get("version", "0.1.0")),
                quality_url=str(reg.get("quality_url", "")),
                observability_url=str(reg.get("observability_url", "")),
                release_policy_version=str(reg.get("release_policy_version", "")),
                release_dataset_id=str(reg.get("release_dataset_id", "")),
                release_dataset_version=str(reg.get("release_dataset_version", "")),
                release_dataset_digest=str(reg.get("release_dataset_digest", "")),
                release_evaluator=str(reg.get("release_evaluator", "")),
                release_threshold_policy_digest=str(reg.get("release_threshold_policy_digest", "")),
                release_artifact_prefixes=tuple(
                    item.strip()
                    for item in str(reg.get("release_artifact_prefixes", "")).split(",")
                    if item.strip()
                ),
                release_redteam_categories=tuple(
                    item.strip()
                    for item in str(reg.get("release_redteam_categories", "")).split(",")
                    if item.strip()
                ),
            ),
            alloydb=AlloyDBSettings(
                instance_uri=str(adb.get("instance_uri", "")),
                database=str(adb.get("database", "agent_registry")),
                user=str(adb.get("user", "registry_app")),
                ip_type=str(adb.get("ip_type", "PRIVATE")),
                table=str(adb.get("table", "agent_cards")),
            ),
            firestore=FirestoreSettings(
                database=str(fs.get("database", "(default)")),
                collection=str(fs.get("collection", "agent_cards")),
            ),
            local=LocalSettings(db_path=str(loc.get("db_path", ""))),
            adapters=raw.get("adapters", {}) or {},
        )
