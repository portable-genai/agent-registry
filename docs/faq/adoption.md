# Adoption FAQ

## Should we consume or fork?

Consume when the shared platform contract and ownership fit. Fork when institutional ownership,
naming or release cadence must be independent. See `docs/ADOPTING.md`.

## Can we retain our existing agent catalog?

Yes. Implement `AgentRegistryPort`, bind it explicitly and run contract, eval and portability
evidence. Preserve the AgentCard wire shape for consumers.

## Is the rename utility destructive by default?

No. It previews and refuses a package-directory collision before writing.
