"""Live feeds (ADR-8): fetched only by the feeds worker, kept as dated snapshots.

Nothing in the API, the services, the agents or ``core`` imports this package
(an import contract enforces it): the API reads what the feeds worker stored
and never touches the network itself.
"""
