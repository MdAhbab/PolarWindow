# ADR-20: The downlink budget runs on sourced or entered radio figures, and gives ranges

**Status:** Accepted
**Date:** 2026-11-11

## Decision

1. **A physical budget, never a score.** For each station pass the contact answer
   gives the data rate the link can carry and the link margin at the rates the
   mission states, in bit/s and dB, each with a range (`lo`/`hi`). There is no
   composite and no verdict. `app/core/rf_link.py` is pure.
   `Eb/N0 = EIRP - FSPL - L_atm + G/T - 10 log10(k_B) - 10 log10(R)`, with
   `FSPL = 20 log10(d_km) + 20 log10(f_GHz) + 92.45`.
2. **It runs only when the figures exist** (ADR-16, item 5). The mission's `comms`
   block needs `eirp_dbw`, `frequency_mhz` and `required_ebn0_db`; `data_rates_kbps`,
   `required_margin_db` and `eirp_tol_db` are optional. If one of the three is
   missing the answer stays "Line of sight only: ..." and names it. With no EIRP the
   sentence is the one it has always been. A frequency outside X-band
   (8200 to 8600 MHz) also gives line of sight only, since no other band's station
   figures are sourced.
3. **Achievable rate** is the highest rate that keeps `required_margin_db` (default
   0, so the rate that just closes) over the required Eb/N0. It is given at the
   weaker end of each pass and at its peak elevation.
4. **The range is explicit.** `value` is clear sky (cumulative distribution 25 %) with
   nominal inputs. `hi` is clear sky with every tolerance favourable. `lo` is the 99 %
   weather point with every tolerance adverse. A loss reads the other way round:
   clear sky is its `lo`.

## What is sourced, what is entered

| Figure | Where it comes from |
|---|---|
| Antenna gain (peak, no atmosphere) and its tolerance | Published: DSN 810-005 module 101 Rev. I Table 2 (70 m, X-only, 8420 MHz) and module 104 Rev. O Table 9 (34 m BWG, X/Ka mode, 8425 MHz) |
| Antenna-microwave noise `T_AMW` and its tolerance | Published: module 101 Table 4, module 104 Table 9 |
| Zenith attenuation at X-band, 25 % and 99 % | Published: module 105 Rev. E Tables 13 to 15, year average, per complex |
| Slant path, atmosphere noise, cosmic background | Module 105 sections 2.1.1 to 2.1.4: `T_M = 255 + 25 CD`, `1/sin(el)` air mass, `T_atm = T_M (1 - 1/L)`, `2.725 K / L`. Below 6 degrees the air mass continues with the Kasten and Young (1989) shape, scaled to meet the flat-Earth value at 6 degrees, so it stays finite. Checked: it reproduces the handbook's zenith sky of 5.04, 5.39 and 5.27 K |
| Lander EIRP, frequency, data rates | Published with the mission's source URL, or entered on the mission record, and labelled as such |
| Required Eb/N0 | Entered. No coding's value is stored: a published one (CCSDS 130.1-G) can be entered with its source, but none is assumed here |

G/T is not stored: it is computed from the published gain and noise with the atmosphere
of the moment, so weather moves both the loss and the noise. DSS-24 (a maser, several
signal paths) and DSS-65 (not in module 104) have no sourced figures; the budget is
not given for them and the note says so.

## Not modelled, and why

- **Pointing loss** (lander and station) and **polarisation loss**: nothing states them
  for a given lander. The EIRP is taken toward Earth.
- **Gain change with elevation:** the peak gain is used. The curves are published as
  figures, not tables; the low end of the range carries only the stated tolerance.
- **DSN scheduling and load**, as in ADR-16: this is what a station could carry, not
  what it is booked for.
- **The uplink**, and any relay link: the figures for them are not published for
  these landers.
- **Rain at the 99 % point beyond the handbook's record**, and sites outside the
  three DSN complexes.

## Consequences

- The numbers reach the AI through the contact section's tool result (ADR-3), so the
  grounding guard accepts exactly these figures and no others.
- Adding a band means adding sourced station figures to the catalogue first.
