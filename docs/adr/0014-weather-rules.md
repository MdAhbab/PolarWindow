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
