"""Independent IM-2 reference, plus guards against comparing mismatched runs."""
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from app.core import belts
from app.validation.compare_spenvis import read_spectrum

FIXTURE = Path(__file__).parents[1] / "fixtures" / "radiation" / "im2-spenvis.csv"


def test_saa_rotation_has_the_published_direction_epoch_and_no_radius_change() -> None:
    xyz = np.array([[belts.RE_KM, 0., 123.]])
    t = datetime(1980, 1, 1, tzinfo=UTC)
    p = belts.saa_corrected_geo("p", "max", [t], xyz)
    e = belts.saa_corrected_geo("e", "max", [t], xyz)
    assert np.degrees(np.arctan2(p[0, 1], p[0, 0])) == pytest.approx(3.)
    assert np.degrees(np.arctan2(e[0, 1], e[0, 0])) == pytest.approx(6.)
    assert np.linalg.norm(p) == pytest.approx(np.linalg.norm(xyz))
    assert np.array_equal(xyz, [[belts.RE_KM, 0., 123.]])
    assert np.allclose(p, belts.saa_corrected_geo("p", "max", [t.astimezone(
        timezone(timedelta(hours=6)))], xyz))
    with pytest.raises(ValueError):
        belts.saa_corrected_geo("p", "max", [t.replace(tzinfo=None)], xyz)


@pytest.mark.skipif(not belts.available(), reason="IRBEM not installed")
def test_im2_corrected_fluences_agree_with_independent_spenvis_run() -> None:
    rows = np.genfromtxt(FIXTURE, delimiter=",", names=True, dtype=None, encoding="utf-8")
    times = [datetime.fromisoformat(t) for t in rows["utc"]]
    xyz = np.c_[rows["x_km"], rows["y_km"], rows["z_km"]]
    seconds = np.array([(t - times[0]).total_seconds() for t in times])
    for particle, energy, column in [("p", 10., "p_gt10"), ("e", 1., "e_gt1")]:
        flux = belts.integral_flux(particle, "max", [energy], times, xyz)[0]
        predicted = belts.fluence(seconds, flux)
        reference = belts.fluence(seconds, rows[column])
        assert abs(predicted / reference - 1.) <= .05


def test_raw_spectrum_rejects_differential_units(tmp_path) -> None:
    p = tmp_path / "spectrum.txt"
    p.write_text("'Flux','cm^-2 MeV^-1 s^-1',1,'Differential Flux','ENERGY'\n")
    with pytest.raises(ValueError, match="integral"):
        read_spectrum(p)
