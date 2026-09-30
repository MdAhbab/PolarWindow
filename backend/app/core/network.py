"""Contact graph and earliest-arrival routing (T1, F4). Pure.

A contact is a stretch of time during which one node can send to another,
with a one-way light time. A message created at node ``src`` at time ``t``
reaches ``dst`` at the earliest time any chain of contacts allows: this is
contact graph routing in its simplest, exact form (Dijkstra over contacts,
as in the CCSDS Schedule-Aware Bundle Routing approach), with no queueing
or data-volume limits, which a lander's link budget would add.

Nodes are strings. Times are seconds on a common axis.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Contact:
    src: str
    dst: str
    start: float
    end: float
    owlt_s: float


def earliest_arrival(contacts: list[Contact], src: str, dst: str, t: float) -> float:
    """Earliest time a message created at ``src`` at ``t`` can reach ``dst``; inf if never.

    A message may wait at a node for a contact to open; it is sent at the
    later of its arrival and the contact's start, and must be sent before the
    contact ends.
    """
    if src == dst:
        return t
    out: dict[str, list[Contact]] = {}
    for c in contacts:
        out.setdefault(c.src, []).append(c)
    best: dict[str, float] = {src: t}
    heap: list[tuple[float, str]] = [(t, src)]
    while heap:
        at, node = heapq.heappop(heap)
        if node == dst:
            return at
        if at > best.get(node, math.inf):
            continue
        for c in out.get(node, []):
            if c.end <= at:
                continue
            send = max(at, c.start)
            arrive = send + c.owlt_s
            if arrive < best.get(c.dst, math.inf):
                best[c.dst] = arrive
                heapq.heappush(heap, (arrive, c.dst))
    return math.inf


def longest_wait(
    contacts: list[Contact], src: str, dst: str, t0: float, t1: float
) -> tuple[float, float, bool]:
    """The longest time a message created in ``[t0, t1]`` waits to reach ``dst``.

    Returns ``(wait_s, created_at, open)``. The worst case is always a
    message created just as a contact from ``src`` ends (or at ``t0``), so
    only those instants are tried: exact, not sampled. ``open`` is True when
    a message created then cannot be delivered before ``t1``: the wait is
    then a lower bound, cut short by the dates.
    """
    starts = {t0}
    for c in contacts:
        if c.src == src and t0 <= c.end <= t1:
            starts.add(c.end)
    worst, when, cut = 0.0, t0, False
    for t in sorted(starts):
        a = earliest_arrival(contacts, src, dst, t)
        if a > t1 + max((c.owlt_s for c in contacts), default=0.0):
            wait, is_open = t1 - t, True
        else:
            wait, is_open = a - t, False
        if wait > worst:
            worst, when, cut = wait, t, is_open
    return worst, when, cut
