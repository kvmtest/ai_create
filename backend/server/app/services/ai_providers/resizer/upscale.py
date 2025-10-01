from PIL import Image
import os
import math
import requests
from app.core.config import settings

def _upscale_image(input_path, output_path):
    response = requests.post(
        "https://api.stability.ai/v2beta/stable-image/upscale/fast",
        headers={
            "authorization": f"Bearer {settings.STABILITY_AI_API_KEY}",
            "accept": "image/*"
        },
        files={
            "image": open(input_path, "rb"),
        },
        data={
            "output_format": "png",
        },
    )

    if response.status_code == 200:
        with open(output_path, 'wb') as file:
            file.write(response.content)
    else:
        raise Exception(str(response.json()))

def ensure_dimension_matched(
    input_image_path,
    output_image_path,
    target_w,
    target_h,
    temp_dir=None
):
    final_img = Image.open(input_image_path)
    curr_w, curr_h = final_img.size

    # Sanity ensure ratio matches exactly (after potential rounding fallback we will enforce by final resize anyway)
    if curr_w * target_h != curr_h * target_w:
        print("⚠️ Ratio not exact after outpaint, will enforce via final resize; slight distortion may occur.")

    if (curr_w, curr_h) == (target_w, target_h):
        final_img.save(output_image_path)
        print("Final size already matches target; done.")
        return final_img
    else:
        MAX_UPSCALE_INPUT_PIXELS = 1_048_576  # Limitation for Stability AI upscale input

        target_pixels = target_w * target_h
        curr_pixels = curr_w * curr_h
        need_enlarge = target_pixels > curr_pixels

        def resize_and_save(img, w, h):
            resized = img.resize((w, h), Image.LANCZOS)
            resized.save(output_image_path)
            return resized

        if not need_enlarge:
            print("Reducing / same size -> local high-quality resize (LANCZOS).")
            return resize_and_save(final_img, target_w, target_h)
        else:
            scale_factor = target_w / curr_w  # same for height when ratios match
            # Heuristic: decide whether to invoke API
            upscale_desirable = (scale_factor > 1.3)  # threshold where AI upscale adds value

            if not upscale_desirable:
                print("Moderate enlargement; using local resize only.")
                return resize_and_save(final_img, target_w, target_h)
            else:
                prep_img = final_img
                prep_w, prep_h = curr_w, curr_h
                prep_pixels = prep_w * prep_h

                if prep_pixels > MAX_UPSCALE_INPUT_PIXELS:
                    # Decide: if target much larger than current and we can benefit from 4x, downscale to limit first
                    if (target_pixels / curr_pixels) > 1.5:
                        # Compute a prep size near the limit with correct ratio
                        ratio = target_w / target_h
                        max_prep_w = int((MAX_UPSCALE_INPUT_PIXELS * ratio) ** 0.5)
                        max_prep_h = int(max_prep_w / ratio)
                        prep_w, prep_h = max_prep_w, max_prep_h
                        print(f"Downscaling large image to {prep_w}x{prep_h} for API input (within limit)")
                        prep_img = final_img.resize((prep_w, prep_h), Image.LANCZOS)
                    else:
                        print("Large source but target not much larger; skipping API and resizing locally.")
                        prep_img = None
                        return resize_and_save(final_img, target_w, target_h)

                # Save prep image to temp
                if temp_dir is None:
                    temp_dir = os.path.dirname(output_image_path)
                prep_path = os.path.join(temp_dir, "3_0_upscale_input.png")
                prep_img.save(prep_path)
                print(f"Calling Stability AI upscale (4x) with input {prep_w}x{prep_h}")
                upscaled_path = os.path.join(temp_dir, "3_1_upscaled.png")
                try:
                    _upscale_image(prep_path, upscaled_path)
                    up_img = Image.open(upscaled_path)
                    up_w, up_h = up_img.size
                    print(f"✅ Upscaled. Result size: {up_w}x{up_h}")
                    # Final adjustment to exact target
                    if (up_w, up_h) != (target_w, target_h):
                        print(f"Resizing upscaled image to final {target_w}x{target_h}")
                        up_img = up_img.resize((target_w, target_h), Image.LANCZOS)
                    up_img.save(output_image_path)
                    return up_img
                except Exception as e:
                    print(f"⚠️ Upscale API failed ({e}); falling back to local resize.")
                    return resize_and_save(final_img, target_w, target_h)
