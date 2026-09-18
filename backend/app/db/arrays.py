"""float32 array <-> bytea. One place, so the wire format cannot drift.

Little-endian is forced explicitly rather than left to the host, so a mask
written on one architecture reads correctly on another. That is not theoretical
here: the golden fixtures are committed and must decode identically everywhere.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt


def encode_f32(arr: npt.NDArray[np.floating[Any]]) -> bytes:
    return np.ascontiguousarray(arr, dtype="<f4").tobytes()


def decode_f32(blob: bytes) -> npt.NDArray[np.float32]:
    return np.frombuffer(blob, dtype="<f4").astype(np.float32)
