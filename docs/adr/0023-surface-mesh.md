# ADR-23: A surface mesh is simulated on entered figures, and no helper is spent to serve another

**Status:** Accepted
**Date:** 2026-11-11

## Decision

This is a simulation on figures the caller enters. It is not a prediction of any real radio,
battery or mission.

1. **Precedent.** A surface-to-surface cellular link is flown practice: Nokia's Lunar Surface
   Communication System was integrated into Intuitive Machines' Athena lander for the IM-2
   mission, to carry rover and hopper data to the lander and on to Earth
   (<https://www.nokia.com/about-us/news/releases/2025/01/07/nokias-cellular-network-ready-for-moon-as-intuitive-machines-completes-final-lunar-lander-installation/>).
   We take the idea, not its parameters; no Nokia figure is used.
2. **Endpoint.** `POST /sites/{site_id}/mesh/simulate` takes nodes (position or waypoints,
   antenna height, battery, own traffic, whether it may help), one radio block and one guard
   block. Every radio, battery, traffic and guard figure is required; a missing one is a 422
   naming the field. Nothing is stored. There is no live-topology endpoint: nothing real
   reports one.
3. **Link.** Two-ray ground reflection over a flat plane of the entered permittivity (Fresnel
   coefficient for the entered polarisation); SNR from the entered bandwidth and noise figure;
   the link closes at the entered SNR threshold. Throughput is the Shannon bound, an upper
   bound. Terrain decides whether a path exists: the straight line between the two antennas
   must be clear of the node's own terrain model, and an uncertain line is reported and not
   used. The first Fresnel zone is reported beside it and does not decide, because between
   antennas a few metres up the ground is always inside that zone (about 5 m deep at 300 m
   and 900 MHz) and its effect is what the two-ray loss already carries; requiring both
   would count the ground twice and no low link would ever be used.
   The longest time without a path to Earth is therefore given twice with the mesh: on the
   links that are certain, and if the uncertain ones hold as well. On real terrain the
   second is where the mesh shows: at Connecting Ridge over 14 days, with a lander and two
   rovers 300 m away, a 2 m height error leaves every low link uncertain or blocked, so the
   certain figure equals direct-only (195 h for the lander) and the other is 159 to 168 h.
4. **Skies per node.** Each node's Earth and Sun come from its own skyline, marched only over
   the bearings Earth and the Sun cover, at a coarser step and shorter range than the site mask.
5. **Radio state machine.** Deep sleep while the direct link is healthy; standby once lost;
   active relay when the loss has lasted longer than the entered threshold; deep sleep again at
   the first healthy step.
6. **Helper guard.** A helper forwards only while sunlit, at or above the entered charge
   cut-off, within its entered energy share per lunar day, and within the entered power cap.
   The refusal names the rule. The helper's own traffic is served first; a finite buffer drops
   and counts overflow.
7. **Routing.** Minimum transmit energy per bit (Dijkstra) over usable links to a node that has
   a healthy direct link.
8. **Answer.** Per node, the longest time without a path to Earth with direct links only and
   with the mesh (the second never exceeds the first), the radio timeline, the routes; per
   helper, forwarded, dropped, energy and lowest charge, each with its margin or why it has
   none. No score, rating or verdict.

## Not modelled

Time-slotted scheduling and real modulation and coding; receive and idle power; a helper's own
loads and charging; ground reflection off real terrain, rocks and diffraction; delay-tolerant
bundle handling; node motion between waypoints; interference and antenna patterns.

## Consequences

Throughput is an upper bound and energy per bit a lower bound, so forwarded volume and helper
cost are stated as such. Results are only as good as the radio figures the caller enters.
