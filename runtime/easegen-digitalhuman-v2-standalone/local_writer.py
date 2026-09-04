"""Redis-free writer callback used only by the Skill's standalone adapter."""

from __future__ import annotations

import os
from pathlib import Path

import cv2

from h_utils.custom import CustomError
from media_runtime import mux_audio_video
from y_utils.logger import logger


def write_video(output_imgs_queue, temp_dir, result_dir, work_id, audio_path, result_queue,
                width, height, fps, watermark_switch=0, digital_auth=0):
    temporary = Path(os.getenv("EASEGEN_DH_LOCAL_TEMP", "temp")) / f"{work_id}-t.mp4"
    requested_output = os.getenv("EASEGEN_DH_LOCAL_OUTPUT")
    requested_output_dir = os.getenv("EASEGEN_DH_LOCAL_OUTPUT_DIR")
    if requested_output_dir:
        output = Path(requested_output_dir) / f"{work_id}.mp4"
    else:
        output = Path(requested_output) if requested_output else Path("result") / f"{work_id}-r.mp4"
    temporary = temporary.expanduser().resolve()
    output = output.expanduser().resolve()
    temporary.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    writer = cv2.VideoWriter(str(temporary), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        result_queue.put([False, f"cannot create temporary video: {temporary}"])
        return

    succeeded = False
    try:
        while True:
            state, reason, frames = output_imgs_queue.get()
            if state is True:
                break
            if state is False:
                raise CustomError(reason)
            for frame in frames:
                writer.write(frame)
        writer.release()
        writer = None
        if watermark_switch or digital_auth:
            raise CustomError("the standalone adapter does not support watermark overlays")
        result = mux_audio_video(audio_path, temporary, output,
                                 timeout=float(os.getenv("EASEGEN_DH_MUX_TIMEOUT", "1800")))
        logger.info(f"standalone digital-human video generated and validated: {result}")
        result_queue.put([True, str(result)])
        succeeded = True
    except Exception as exc:
        logger.error(f"standalone video finalization failed [{work_id}]: {exc}")
        result_queue.put([False, str(exc)])
    finally:
        if writer is not None:
            writer.release()
        if succeeded:
            temporary.unlink(missing_ok=True)
