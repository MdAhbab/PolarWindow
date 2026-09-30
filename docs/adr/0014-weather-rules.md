# ADR-14: Launch weather is a list of rules, each with its own evidence; never one number

**Status:** Accepted
**Date:** 2026-09-26
**Relates to:** ADR-8, invariants 9 and 12

## Context

Launch weather is decided against written rules (NASA-STD-4010A lightning
criteria, range rules, each vehicle's limits) by the launch weather officer.
Some rules a forecast model can answer (wind at tower height, temperature,
rain); some only partly (thick cloud layers, cumulus tops); some not at all
(lightning in the last 30 minutes, field mills, anvils).

## Decision

1. **Rules are data** (`data/catalogues/weather_rules.json`): the verbatim text,
   its source, the threshold in the source's own unit, the variable and height,
   and a class: `model`, `proxy` or `observation`.
2. **Model rules**: for each ensemble system separately (GEFS, ECMWF ENS, AIFS
   ENS), the share of runs that break the rule at the launch time, with its
   interval (ADR-9 `Share`). Systems are never pooled; when their intervals do
   not overlap, the rule says the models disagree. A deterministic forecast
   (NWS, HRRR, GEOS-FP) is shown as "one forecast: over / under".
3. **Proxy rules** say "the model sees the ingredients in k of n runs", not the
   rule's probability.
4. **Observation rules** get no forecast number. They show the 45th Weather
   Squadron's published forecast (entered with its PDF link, never scraped),
   lightning seen by GOES GLM near the pad in the last 30 minutes, and the
   month-and-hour history from NASA's GLM thunder-hour record.
5. **No overall chance of launch.** The decision belongs to the launch team.
6. **A rule is "checked" only after a hindcast** against observations (Brier
   skill at least 0.1 against month-and-hour climatology at up to 48 hours,
   reliability within 0.1 in bins of 30 or more); until then it says
   "not yet checked".

## Amendment (2026-09-29)

1. **"Checked against observations" over multiple years:** rule verification
   evaluates models against historical station records (Cape Canaveral ASOS KXMR
   and Vandenberg ASOS KVBG via Iowa Environmental Mesonet archives) and the
   multi-year GEFSv12 reforecast (2000-2019, 00 UTC runs). A rule requires Brier
   skill score (BSS >= 0.1 computed when >= 10 cases exceed the threshold) and
   continuous ranked probability score (CRPS and fair CRPS skill) with 95 %
   confidence intervals resampled by month, alongside reliability bins with
   Wilson intervals (`make hindcast-reforecast`).
2. **Forecast disagreement flag:** deterministic forecasts (HRRR 3 km, NWS pad
   hourly) sit beside ensemble distributions. A single forecast disagrees with
   GEFS when its call falls on the side of the threshold that GEFS's 95 % credible
   interval excludes. NWS and HRRR disagree when on opposite sides of the rule's
   limit and further apart than HRRR's measured 10 m error; disagreements are
   explicitly surfaced via `disagreement_note` on the launch weather row.
3. **High-resolution HRRR archive verification:** HRRR v4 is verified across
   2021-2025 (`make hindcast-hrrr`) using byte-range queries directly on NOAA's
   AWS Open Data bucket, scoring pad 10 m winds against KXMR and KVBG observations.
