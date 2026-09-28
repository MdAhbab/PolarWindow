# ADR-16: Contact is geometry first; planned relays are ranges; DSN load is not modelled

**Status:** Accepted
**Date:** 2026-09-26

## Decision

1. **"Time in contact with Earth" keeps its meaning** (Earth above the site's
   skyline). "Time a ground station can hear the lander" is a new, separately
   named number: Earth above the skyline and the Moon above a station's own
   horizon mask (DSN 810-005 module 301; other stations' masks are *assumed*).
2. **Relays with real orbits** (LRO, Danuri, Chandrayaan-2, CAPSTONE, from JPL
   Horizons) are used to check the pass calculation; none is a relay for CLPS
   landers, and the product never calls them one.
3. **Planned relays** (Lunar Pathfinder, Intuitive Machines' data-relay
   satellites) have no public orbit phase. Their contribution is a range over
   every phase: "3 to 7 hours through the relay, if it flies as planned",
   with each relay's launch status beside it. When one flies and publishes an
   orbit, it becomes a real timeline.
4. **DSN scheduling load is not modelled.** The product shows when a station
   *can* hear, what DSN Now shows was actually tracked, and passes the project
   manager has booked (entered and audited), which take priority.
5. **A link budget runs only on sourced or entered radio figures**; otherwise
   the answer says "line of sight only: the lander's radio power is not
   published".
6. Contact plans export in the ION-DTN contact-plan format as well as CSV.
