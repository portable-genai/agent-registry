"""On-prem deployment profile adapters: fail-fast Google Distributed Cloud placeholders.

The ``onprem`` profile is the documented migration target. Every adapter here constructs
cleanly with a single :class:`~agent_registry.config.Settings` argument and structurally
satisfies the same Protocol as the managed and local families (so the contract tests prove
interface parity), but raises ``NotImplementedError`` from every method. Porting the
catalog to an on-premise platform is *only* a matter of filling these bodies in: the domain
and the wiring above the adapter layer are unchanged. No third-party product is named.
"""
