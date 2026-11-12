# Design glossary

How PolarWindow names things on screen. Plain words come first and the technical term second, in brackets, so a bright general reader understands the label and an expert still finds the term. The term is never dropped. Hints are what the "what this means" buttons and tooltips say.

Audit behind it: `.local/review/audit-2026-11-12/flow/jargon.md` (every place a term is the only label, with its source).

## Terms

| Term | Plain-words label | Hint (one sentence) | Write it like this |
|---|---|---|---|
| CLPS | NASA's commercial Moon landings | NASA buys deliveries to the Moon from private companies under Commercial Lunar Payload Services. | NASA's commercial Moon landings (CLPS) |
| Task order | NASA contract | NASA's contract for one delivery under CLPS. | NASA task order CP-11 |
| Payload | Instrument on board | An instrument or experiment the lander carries. | 3 payloads (instruments on board) |
| Record | The mission's record | What is published about the mission, each fact with its source. | The mission's record |
| Step | Step | One of six stages every mission goes through (Ready, Launch, Trip, Surface, Contact, Return), each answering one question. | Step 4 · Surface |
| Scenario | Scenario | A what-if worked out from assumed values, always labelled and hatched, never written into the mission's record. | Scenario · When and from where can it launch? |
| Default | Default from past flights | A value taken from a named past flight or catalogue when the record gives none. | Default: as IM-2, the last flight of this lander |
| Computed / published / entered / assumed | Worked out / published / entered by your team / assumed | Every number says which of these it is, and carries its margin. | N h ± m h, worked out |
| Margin (±) | Margin | How far a number could be off, from the terrain map's error and the timing. | N h ± m h |
| At least (≥) | At least | The stretch runs past the start or end of the chosen dates, so the true length is at least this. | at least 112 h (≥112 h) |
| Too close to call | Too close to call | Two sites' figures overlap within their margins, so their order is not known. | Too close to call |
| Lunar day | One lunar day | From one sunrise to the next at the same spot: about 29.5 Earth days. | one lunar day, 709 hours |
| Time in sunlight | Time in sunlight | Hours the Sun is above the local skyline on these dates. | Time in sunlight: 73% of the time |
| Time in contact with Earth | Time in contact with Earth | Hours Earth is above the local skyline; a dish on Earth must also be listening. | Time in contact with Earth |
| Longest night | Longest night | The longest stretch with the Sun below the skyline; a solar-powered lander must last it on batteries. | Longest night: 64 h |
| Longest time without contact | Longest time without contact | The longest stretch with Earth below the skyline, when no message can get through directly. | Longest time without contact |
| Longest time in shadow | Longest time in shadow | On the way to the Moon, the longest stretch the Sun is hidden by Earth or the Moon. | Longest time in shadow |
| Autonomy | Time working alone | The longest time both dark and out of contact, plus a safety share: the lander runs on stored commands and its battery. | 11 hours working alone |
| Battery limit (survival) | Battery limit | How long the batteries keep the lander alive without sunlight: entered by the team, or assumed and hatched. | 120 h battery limit (assumed) |
| Horizon mask | Skyline | The outline of hills around the site seen from the ground; the Sun or Earth below it is blocked. | The skyline from Connecting Ridge |
| Terminator | Day and night line | The line between day and night on the Moon. | the day and night line (terminator) |
| PSR | Shadowed crater | A crater floor the Sun never reaches, where water ice can survive. | Beside a shadowed crater (PSR) |
| Grazing | Skims the skyline | The Sun or Earth only skims the skyline, so the moment it is blocked cannot be timed. | skims the skyline: time unsure (grazing) |
| Launch period / window | Launch days / launch time | The days a launch can reach the planned path, and the minutes on each day it can lift off. | Launch days (launch period) |
| Launch opportunity | Launch opportunity | One day and time when a launch reaches the planned path. It is a time, never a probability. | 12 launch opportunities |
| TLI | Leaving Earth for the Moon | The engine burn that sends the spacecraft from Earth orbit toward the Moon (trans-lunar injection). | leaving Earth for the Moon (TLI) |
| Burn | Engine firing | A firing of the engine to change speed or direction. | 8 engine firings (burns) |
| TCM | Correction on the way | A small burn on the way that fixes the path. | Corrections on the way |
| Delta-v | Speed added | How much speed an engine burn adds or removes; the fuel budget is counted in it. | Speed added (delta-v): 88.7 m/s |
| Equal-pull point | Where the Moon's pull wins | The distance from the Moon at which its gravity outpulls Earth's on the spacecraft. | Where the Moon's pull wins |
| Ensemble forecast | Forecast runs | Many runs of a weather model from slightly different starts; the share that break a launch rule is shown, not a verdict. | US forecast runs that break it (NOAA GEFS) |
| Ground station | Ground station | A big radio dish on Earth that talks to spacecraft. | Time a ground station can hear the lander |
| DSN | NASA's deep-space dishes | NASA's three dish sites, in California, Spain and Australia, that talk to deep-space missions. | NASA's deep-space dishes (Deep Space Network) |
| Station mask | What a dish can see over | The lowest angle above its horizon at which a dish can point, all the way round. | What each dish can see over (station masks) |
| Relay | Relay satellite | A satellite orbiting the Moon that passes messages between the lander and Earth. | Through a relay |
| Line of sight | Straight line clear | A straight, unblocked line between two antennas. | Straight line clear (line of sight) |
| Fresnel zone | Room for the radio wave | The wider zone around the straight line that a radio wave needs clear to arrive at full strength. | Room for the radio wave (Fresnel zone) |
| Downlink / uplink | Lander to Earth / Earth to lander | The direction the radio signal travels. | Radio frequency, lander to Earth (downlink) |
| EIRP | Radio power | How strongly the lander's antenna sends toward Earth, transmitter and antenna together. | Radio power (EIRP, dBW) |
| G/T | Dish sensitivity | How well a ground dish hears faint signals: its gain over its own noise. | Ground dish sensitivity (G/T, dB/K) |
| Eb/N0 | Signal needed per bit | Signal energy per bit over background noise; a radio needs a minimum to decode data. | Signal needed per bit (Eb/N0, dB) |
| Link margin | Spare signal | How much stronger the signal is than the minimum needed. | Spare signal kept in hand (link margin, dB) |
| Downlink budget | Radio link to Earth | The sum that says whether the lander's signal reaches Earth strong enough at a given data rate. | Radio link to Earth (downlink budget) |
| DTN / ION contact plan | Contact timetable for networking software | When each link is open, in the format delay-tolerant networking software (ION) reads. | Contact plan for networking software (ION, DTN) |
| SPICE | NASA's navigation toolkit | NASA's toolkit for spacecraft positions and timing, used by navigation engineers. | Download for NASA's navigation toolkit (SPICE) |
| Landing ellipse (3-sigma) | Where it could come down | The oval the lander comes down inside nearly every time. | Where it could come down (landing ellipse, 3-sigma) |
| Slope | Slope | How steep the ground is; above its limit a lander can tip over. | Slope across the landing area |
| Bus temperature | Temperature inside the lander | The temperature in the lander's main body, where its electronics are. | Coldest inside the lander (bus) |
| State of charge | Battery charge | How full the battery is, as a percentage. | Lowest battery charge |
| Mesh | Rovers relaying for each other | Rovers and the lander pass each other's data along so whichever sees Earth can send it. | Rovers relaying for each other |
| Kp | Magnetic storm level | A 0 to 9 scale of how disturbed Earth's magnetic field is; 5 and above is a storm. | magnetic storm level 2.7 of 9 (Kp) |
| Protons above 10 MeV (pfu) | Fast protons from the Sun | Fast particles from the Sun; NOAA declares a radiation storm above 10 pfu. | Fast protons (above 10 MeV): 0.12 pfu |
| X-ray flare class | Solar flare size | Flare size from A (smallest) through B, C and M to X (largest). | X-ray flares: class B |
| Bz | Sun's magnetic field, north-south | The north-south part of the Sun's magnetic field near Earth; southward helps storms start. | Magnetic field from the Sun, north-south (Bz) |
| Radiation belts | Radiation belts | Zones around Earth that trap fast particles; a spacecraft crosses them on the way out. | Time in the radiation belts |
| Cosmic-ray dose | Cosmic-ray dose | Radiation from outside the solar system absorbed per day, before any shielding. | Cosmic-ray dose on the way |
| Solar particle event | Burst of particles from the Sun | A burst of fast protons from the Sun lasting hours to days. | Solar particle events during the trip |
| Screening estimate | First look | A first look from public models, not a figure for design. | Radiation on the way: a first look |
| Booster landing zone | Where the booster comes down | Where the rocket's first stage lands after launch. | Booster landing zone |
| Droneship | Landing ship at sea | An uncrewed ship a booster lands on. | lands on a ship at sea (droneship) |
| Splashdown zone | Where a capsule lands at sea | Where a capsule returning from the Moon comes down in the sea. | Splashdown zone |
| UTC | World time | Clock time with no time zone or daylight saving. | 27 Feb 2025, 00:16 UTC |
| LOLA / LRO | NASA's Moon height map / orbiter | Heights measured by the laser on NASA's Lunar Reconnaissance Orbiter, which also took the photographs. | NASA's height map of the pole (LOLA) |
| Run log | How the AI got this | The tools the AI called and where every number in its answer came from. | How the AI got this |
| Rule-based answer | Answered from rules | No AI model answered, so fixed rules wrote the answer from the same measurements. | Answered from rules, not a model |

## One name for one thing

| Thing | Use | Not |
|---|---|---|
| The site area of the app | Landing sites (titles, crumbs, guide); Sites (narrow nav only) | Candidate landing sites, Landing site pages |
| A surveyed candidate place | site | spot, chosen spot |
| A mission's target | landing spot | target (in sentences), site |
| What a page covers in time | dates | window, evaluation window, reference window, period |
| Earth above the skyline | Time in contact with Earth | Earth in view (in labels), earth contact, contact (alone) |
| A dish hearing the lander | Time a ground station can hear the lander | Time a ground station can hear it, the Deep Space Network can hear, NASA's big dishes |
| One day and time a launch can go | launch opportunity | chance to launch, possible launch time, opportunity (alone) |
| The longest gap with no direct contact | Longest time without contact | Without contact (alone), blackout, comms blackout |
| The longest gap counting relays | Longest message wait | (keep; say "counting relays" in its hint) |
| Sun below the skyline on the surface | night | dark period, dark gap, darkness |
| The six stages | steps | sections, phases (phases is for a scenario being worked out) |
| A what-if | scenario; "What if…" only as the link into one | named defaults, precedent (as titles) |
| A mission the team adds | project | (Settings tab "Project" becomes "Team") |
| The paper output | Printable report | Report (alone), one-pager |
| A table download | Download as a spreadsheet (CSV) | Download as CSV, Spreadsheet (CSV) |

## Words that never appear

best, safest, recommended, score, go or no-go, likely, chance (including "chance to launch" and "chance of success"), possible launch time, overall rank. The Compare page orders by one number at a time and says which number; a place in that order is never a verdict on the site.
