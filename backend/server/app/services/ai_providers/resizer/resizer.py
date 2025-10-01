import os
from pathlib import Path

from .outpaint import ensure_aspect_ratio_matched
from .upscale import ensure_dimension_matched 
from .relayout import relayout_if_needed
import shutil
import uuid

def resize(image_path: str, target_w: int, target_h: int, provider: str, keep_temp: bool=False) -> str:

    input_path = Path(image_path)
    random_id = str(uuid.uuid4())[:8]  # Short 8-character random ID
    output_filename = f"{input_path.stem}_adapted_{target_w}x{target_h}_{random_id}.png"
    output_path = input_path.parent / output_filename

    temp_dir = os.path.join(os.getcwd(), "temp", "temp_" + os.path.splitext(os.path.basename(output_path))[0])
    os.makedirs(temp_dir, exist_ok=True)

    # 1. Generate a good base composition at a supported ratio (relayout picks closest among a small set)
    relayouted_image_path = os.path.join(temp_dir, "1_relayouted.png")
    relayouted = relayout_if_needed(
        input_image_path=input_path,
        output_image_path=relayouted_image_path,
        target_w=target_w,
        target_h=target_h,
        provider=provider
    )

    # 2. Exact aspect ratio enforcement (no tolerance).
    outpainted_image_path = os.path.join(temp_dir, "2_outpainted.png")
    outpainted = ensure_aspect_ratio_matched(
        input_image_path=relayouted_image_path,
        output_image_path=outpainted_image_path,
        target_w=target_w,
        target_h=target_h
    )

    # 3. Size matching phase (after ratio is exact) using upscale API or local resize.
    final_img = ensure_dimension_matched(
        input_image_path=outpainted_image_path,
        output_image_path=output_path,
        target_w=target_w,
        target_h=target_h,
        temp_dir=temp_dir
    )

    # Cleanup temp files
    if not relayouted:
        os.remove(relayouted_image_path)
    if not outpainted:
        os.remove(outpainted_image_path)
    if not keep_temp:
        try:
            shutil.rmtree(temp_dir)
            print(f"Temporary directory {temp_dir} removed.")
        except OSError:
            print(f"Temporary directory {temp_dir} not removed.")

    return str(output_path)