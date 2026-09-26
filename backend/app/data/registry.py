"""Every dataset POLAR WINDOW uses, in one list.

This list is the single source for three things that used to drift apart:

* what ``run.py`` (through ``polar-data sync``) downloads after the app starts,
* the "Required data" table in the README (``polar-data readme`` writes it,
  and a test fails if the README and this list disagree),
* where each number's data came from (source URL, and the data.nasa.gov
  catalogue record where NASA lists the dataset there).

Tiers
-----
``core``        the app cannot answer without it; fetched first.
``lifecycle``   a lifecycle section (trip, launch, contact) needs it; the
                surface numbers work without it.
``validation``  used to check our numbers against flown missions or an
                independent measurement; never needed at runtime.
``bulk``        large archives reduced to small climatologies by a job; fetched
                only on request (``polar-data sync --tier bulk``).

Live feeds (weather forecasts, space weather now, DSN Now) are not here: they
are fetched on a schedule by the feeds worker and kept as dated snapshots
(ADR-8). This list is for files that are downloaded once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from app.core.kernels import LIFECYCLE_KERNELS, REQUIRED_KERNELS, KernelSpec

Tier = Literal["core", "lifecycle", "validation", "bulk"]
TIERS: Final[tuple[Tier, ...]] = ("core", "lifecycle", "validation", "bulk")

#: How a dataset arrives. ``kernel`` goes through ``core.kernels`` (one code
#: path for every SPICE file); ``file`` through ``data.download``; ``lola_*``
#: through the LOLA reader, which knows the product layout; ``seed`` is built
#: locally from other datasets; ``cmr`` lists a NASA Earthdata collection's
#: files through the Common Metadata Repository and fetches each one.
Method = Literal["kernel", "file", "lola_regional", "lola_fine", "seed", "cmr"]

DATA_NASA: Final[str] = "https://data.nasa.gov/dataset"
NAIF_PDS_CLPS: Final[str] = (
    "https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels"
)


@dataclass(frozen=True, slots=True)
class Dataset:
    id: str
    title: str
    provider: str
    tier: Tier
    method: Method
    #: Where the bytes come from (first entry) and fallbacks, in order.
    urls: tuple[str, ...]
    #: Path under ``data/``.
    dest: str
    #: Approximate size on disk, for the README and for progress.
    size_bytes: int
    #: What breaks without it, in plain words.
    used_for: str
    licence: str
    #: The data.nasa.gov record for this dataset, where NASA lists one.
    catalogue: str | None = None
    sha256: str | None = None
    min_bytes: int = 1
    #: A free account or key the download needs (``None`` = no account).
    needs_key: str | None = None
    #: For ``method="cmr"``: the Earthdata collection concept id.
    cmr_collection: str | None = None
    #: False when the download address could not be reached to confirm it.
    #: The README says so next to the dataset rather than implying it works.
    address_confirmed: bool = True

    @property
    def source(self) -> str:
        return self.urls[0] if self.urls else ""


_KERNEL_CATALOGUE: Final[dict[str, str]] = {}


def _kernel(spec: KernelSpec, tier: Tier) -> Dataset:
    return Dataset(
        id=f"kernel:{spec.name}",
        title=f"SPICE {spec.kind} {spec.name}",
        provider="NASA JPL NAIF",
        tier=tier,
        method="kernel",
        urls=(spec.url, *spec.mirrors),
        dest=f"kernels/{spec.name}",
        size_bytes=spec.min_bytes,
        used_for=spec.why,
        licence="US government work (public domain)",
        catalogue=_KERNEL_CATALOGUE.get(spec.name),
        sha256=spec.sha256,
        min_bytes=spec.min_bytes,
    )


_LOLA_PDS: Final[str] = (
    "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/polar/img"
)

_GOLDSTONE: Final[str] = (
    "https://pds-geosciences.wustl.edu/lunar/gdscc-l-dss14_dss13_dss15_dss25-5-v1/lram_10xx/data"
)

_SPECIFIC: Final[tuple[Dataset, ...]] = (
    Dataset(
        id="lola:ldem_80s_80m",
        title="LOLA south polar elevation model, 80 m (LDEM_80S_80M)",
        provider="NASA LRO LOLA / PDS Geosciences",
        tier="core",
        method="lola_regional",
        urls=(f"{_LOLA_PDS}/ldem_80s_80m.img",),
        dest="dem/regional_80m.npz",
        size_bytes=115_520_000,
        used_for="Terrain for every site south of 80 deg S: the skyline that decides "
        "sunlight and contact with Earth, the map tiles and site placement.",
        licence="US government work (public domain)",
        catalogue=f"{DATA_NASA}/lro-moon-laser-altimeter-4-gdr-v1-0",
        min_bytes=100_000_000,
    ),
    Dataset(
        id="lola:ldem_80s_20m_windows",
        title="LOLA south polar elevation model, 20 m (LDEM_80S_20M), windows around each site",
        provider="NASA LRO LOLA / PDS Geosciences",
        tier="core",
        method="lola_fine",
        urls=(f"{_LOLA_PDS}/ldem_80s_20m.img",),
        dest="dem/fine/",
        size_bytes=40_000_000,
        used_for="The near skyline at each site. Only a 20 km window per site is read, "
        "by HTTP range requests; the 1.85 GB file is never downloaded whole.",
        licence="US government work (public domain)",
        catalogue=f"{DATA_NASA}/lro-moon-laser-altimeter-4-gdr-v1-0",
    ),
    Dataset(
        id="seed:site-masks",
        title="Skylines and reference numbers for every site (built locally)",
        provider="Built from the LOLA and SPICE data above",
        tier="core",
        method="seed",
        urls=(),
        dest="(database)",
        size_bytes=0,
        used_for="The 1,440-bearing skyline and the four numbers for each candidate and "
        "mission site; built once, then every answer is a lookup.",
        licence="-",
    ),
    Dataset(
        id="grail:gggrx_1200a_sha",
        title="GRAIL lunar gravity field GRGM1200A (spherical harmonics)",
        provider="NASA GRAIL / PDS Geosciences",
        tier="lifecycle",
        method="file",
        urls=(
            "https://pds-geosciences.wustl.edu/grail/grail-l-lgrs-5-rdr-v1/"
            "grail_1001/shadr/gggrx_1200a_sha.tab",
        ),
        dest="gravity/gggrx_1200a_sha.tab",
        size_bytes=88_059_844,
        used_for="The Moon's lumpy gravity for the trip and lunar orbit: without it a "
        "low lunar orbit drifts kilometres a day from where it really is.",
        licence="US government work (public domain)",
        catalogue=f"{DATA_NASA}/grail-moon-lgrs-derived-gravity-science-data-products-v1-0",
        min_bytes=88_000_000,
    ),
    Dataset(
        id="grail:gggrx_1200a_sha_label",
        title="GRAIL GRGM1200A label (reference radius, GM, normalisation)",
        provider="NASA GRAIL / PDS Geosciences",
        tier="lifecycle",
        method="file",
        urls=(
            "https://pds-geosciences.wustl.edu/grail/grail-l-lgrs-5-rdr-v1/"
            "grail_1001/shadr/gggrx_1200a_sha.lbl",
        ),
        dest="gravity/gggrx_1200a_sha.lbl",
        size_bytes=10_665,
        used_for="Reads the gravity field correctly: the label defines its units and frame.",
        licence="US government work (public domain)",
        catalogue=f"{DATA_NASA}/grail-moon-lgrs-derived-gravity-science-data-products-v1-0",
        min_bytes=5_000,
    ),
    Dataset(
        id="clps:im1_cruise",
        title="IM-1 Odysseus reconstructed trajectory (CLPS SPICE archive)",
        provider="NASA JPL NAIF / PDS",
        tier="validation",
        method="file",
        urls=(f"{NAIF_PDS_CLPS}/spk/clps_to2im_im1_cru_rec_240216_240221_v01.bsp",),
        dest="clps/clps_to2im_im1_cru_rec_240216_240221_v01.bsp",
        size_bytes=71_680,
        used_for="Checks our trip and launch-time calculations against where IM-1 "
        "actually flew (February 2024).",
        licence="US government work (public domain)",
        min_bytes=50_000,
    ),
    Dataset(
        id="clps:im2_cruise",
        title="IM-2 Athena reconstructed trajectory (CLPS SPICE archive)",
        provider="NASA JPL NAIF / PDS",
        tier="validation",
        method="file",
        urls=(f"{NAIF_PDS_CLPS}/spk/clps_prime1_im2_cru_rec_250227_250306_v01.bsp",),
        dest="clps/clps_prime1_im2_cru_rec_250227_250306_v01.bsp",
        size_bytes=9_505_792,
        used_for="Checks our trip and launch-time calculations against IM-2 (March 2025).",
        licence="US government work (public domain)",
        min_bytes=9_000_000,
    ),
    Dataset(
        id="clps:bgm1_cruise",
        title="Blue Ghost Mission 1 reconstructed trajectory (CLPS SPICE archive)",
        provider="NASA JPL NAIF / PDS",
        tier="validation",
        method="file",
        urls=(f"{NAIF_PDS_CLPS}/spk/clps_to19d_bgm1_cru_rec_250115_250302_v01.bsp",),
        dest="clps/clps_to19d_bgm1_cru_rec_250115_250302_v01.bsp",
        size_bytes=23_833_600,
        used_for="Checks the Earth-orbit loops and lunar orbit against Blue Ghost 1 "
        "(January to March 2025).",
        licence="US government work (public domain)",
        min_bytes=23_000_000,
    ),
    Dataset(
        id="clps:peregrine_cruise",
        title="Peregrine Mission One reconstructed trajectory (CLPS SPICE archive)",
        provider="NASA JPL NAIF / PDS",
        tier="validation",
        method="file",
        urls=(f"{NAIF_PDS_CLPS}/spk/clps_to2ab_apm1_cru_rec_240108_240118_v02.bsp",),
        dest="clps/clps_to2ab_apm1_cru_rec_240108_240118_v02.bsp",
        size_bytes=863_232,
        used_for="Tests that the trip model notices an unmodelled push: Peregrine's "
        "propellant leak (January 2024).",
        licence="US government work (public domain)",
        min_bytes=800_000,
    ),
    Dataset(
        id="dsn:810-005-301",
        title="DSN Telecommunications Link Design Handbook 810-005, module 301 (coverage and "
        "geometry, antenna horizon masks)",
        provider="NASA JPL Deep Space Network",
        tier="lifecycle",
        method="file",
        urls=("https://deepspace.jpl.nasa.gov/dsndocs/810-005/301/301O.pdf",),
        dest="dsn/810-005-301O.pdf",
        size_bytes=3_073_743,
        used_for="Each Deep Space Network antenna's real horizon: the lowest elevation "
        "at which it can hear the Moon, by direction.",
        licence="US government work (public domain)",
        min_bytes=1_000_000,
    ),
    Dataset(
        id="goldstone:south-pole-dem",
        title="Goldstone radar elevation model of the lunar south pole (~150 m)",
        provider="NASA JPL Goldstone Solar System Radar / PDS Geosciences",
        tier="validation",
        method="file",
        urls=(f"{_GOLDSTONE}/south_pole_mosaic.img",),
        dest="validation/goldstone/south_pole_mosaic.img",
        size_bytes=64_000_000,
        used_for="An independent terrain measurement (radar, not laser) to check the "
        "skylines built from LOLA.",
        licence="US government work (public domain)",
        catalogue=f"{DATA_NASA}/goldstone-moon-dss14-dss13-dss15-dss25-5-altimetry-v1-0",
        min_bytes=64_000_000,
    ),
    Dataset(
        id="goldstone:south-pole-dem-label",
        title="Goldstone south pole elevation model label (projection and units)",
        provider="NASA JPL Goldstone Solar System Radar / PDS Geosciences",
        tier="validation",
        method="file",
        urls=(f"{_GOLDSTONE}/south_pole_mosaic.lbl",),
        dest="validation/goldstone/south_pole_mosaic.lbl",
        size_bytes=4_853,
        used_for="Reads the Goldstone elevation model correctly.",
        licence="US government work (public domain)",
        catalogue=f"{DATA_NASA}/goldstone-moon-dss14-dss13-dss15-dss25-5-altimetry-v1-0",
        min_bytes=2_000,
    ),
    Dataset(
        id="spdf:omni2-hourly",
        title="OMNI hourly solar wind, geomagnetic and solar indices, 1963 to date",
        provider="NASA GSFC Space Physics Data Facility",
        tier="lifecycle",
        method="file",
        urls=("https://spdf.gsfc.nasa.gov/pub/data/omni/low_res_omni/omni2_all_years.dat",),
        dest="spaceweather/omni2_all_years.dat",
        size_bytes=180_000_000,
        used_for="Solar activity (F10.7, Ap) that sets air drag in Earth orbit, and the "
        "history of solar storms and proton events used to check radiation estimates.",
        licence="US government work (public domain)",
        catalogue=f"{DATA_NASA}/omni-hourly-data-set",
        min_bytes=50_000_000,
        # spdf.gsfc.nasa.gov refused connections on 2026-09-26 from both the
        # shell and a browser; the path is the one data.nasa.gov lists.
        address_confirmed=False,
    ),
    Dataset(
        id="ghrc:ksc-field-mill",
        title="KSC Advanced Ground Based Field Mill network, 1997-2012",
        provider="NASA MSFC GHRC DAAC",
        tier="bulk",
        method="cmr",
        urls=("https://data.ghrc.earthdata.nasa.gov/ghrcw-protected/kscmill__1/",),
        dest="bulk/kscmill/",
        size_bytes=1_500_000_000_000,
        cmr_collection="C1979872892-GHRC_DAAC",
        used_for="How often the electric field at Kennedy exceeds the launch limit, by "
        "month and hour: the history behind the field-mill launch rule.",
        licence="US government work (public domain)",
        catalogue=f"{DATA_NASA}/ksc-advanced-ground-based-field-mill-v1-7b0b5",
        needs_key="NASA Earthdata Login (free)",
    ),
    Dataset(
        id="ghrc:glm-thunder-hours",
        title="Combined GLM hourly thunder-hour data, 2019-2025",
        provider="NASA MSFC GHRC DAAC",
        tier="bulk",
        method="cmr",
        urls=("https://data.ghrc.earthdata.nasa.gov/ghrcw-protected/glmhth__1/",),
        dest="bulk/glm_thunder_hours/",
        size_bytes=2_557 * 30_000_000,
        cmr_collection="C3894650367-GHRC_DAAC",
        used_for="How often lightning is seen near each launch pad, by month and hour, "
        "for dates beyond the weather forecast.",
        licence="US government work (public domain)",
        catalogue=f"{DATA_NASA}/combined-geostationary-lightning-mapper-glm-hourly-thunder-hour-data-product",
        needs_key="NASA Earthdata Login (free)",
    ),
)

DATASETS: Final[tuple[Dataset, ...]] = (
    tuple(_kernel(s, "core") for s in REQUIRED_KERNELS)
    + tuple(_kernel(s, "lifecycle") for s in LIFECYCLE_KERNELS)
    + _SPECIFIC
)


def by_id(dataset_id: str) -> Dataset:
    for d in DATASETS:
        if d.id == dataset_id:
            return d
    raise KeyError(dataset_id)


def in_tiers(tiers: tuple[Tier, ...]) -> tuple[Dataset, ...]:
    return tuple(d for d in DATASETS if d.tier in tiers)
