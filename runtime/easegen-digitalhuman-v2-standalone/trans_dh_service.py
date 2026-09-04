"""Spawn-safe adapter around the external engine's native HeyGem extension."""

from service import trans_dh_service as _native
from local_writer import write_video


_native.write_video = write_video
TransDhTask = _native.TransDhTask


def __getattr__(name):
    return getattr(_native, name)
