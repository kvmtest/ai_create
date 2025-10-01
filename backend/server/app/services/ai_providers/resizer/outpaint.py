import math
from PIL import Image
import requests
from app.core.config import settings

def _outpaint_image(
    input_image_path: str,
    output_image_path: str,
    left: int,
    right: int,
    up: int,
    down: int,
    output_format: str = "png"
):
    response = requests.post(
        "https://api.stability.ai/v2beta/stable-image/edit/outpaint",
        headers={
            "authorization": f"Bearer {settings.STABILITY_AI_API_KEY}",
            "accept": "image/*"
        },
        files={
            "image": open(input_image_path, "rb")
        },
        data={
            "left": left,
            "right": right,
            "up": up,
            "down": down,
            "output_format": output_format,
            "creativity": 0.3
        },
    )

    if response.status_code == 200:
        with open(output_image_path, 'wb') as file:
            file.write(response.content)
    else:
        raise Exception(str(response.json()))

def _minimal_expansion(base_w, base_h, target_w, target_h):
    # Simplify the target ratio to its smallest integer form (e.g., 1920/1080 -> 16/9)
    common_divisor = math.gcd(target_w, target_h)
    tr_w = target_w // common_divisor
    tr_h = target_h // common_divisor

    # We need to find the smallest integer k, such that:
    # new_w = k * tr_w >= base_w  => k >= base_w / tr_w
    # new_h = k * tr_h >= base_h  => k >= base_h / tr_h
    k_w = math.ceil(base_w / tr_w)
    k_h = math.ceil(base_h / tr_h)
    k = max(k_w, k_h)

    # The new dimensions are k times the simplified ratio
    new_w = k * tr_w
    new_h = k * tr_h
    left = (new_w - base_w) // 2
    right = new_w - base_w - left
    up = (new_h - base_h) // 2
    down = new_h - base_h - up
    return new_w, new_h, left, right, up, down

def ensure_aspect_ratio_matched(
    input_image_path: str,
    output_image_path: str,
    target_w: int,
    target_h: int
):
    input_img = Image.open(input_image_path)
    base_w, base_h = input_img.size
    # Check if aspect ratio is already exact
    if base_w * target_h == base_h * target_w:
        print("Aspect ratio already exact; no outpainting needed.")
        input_img.save(output_image_path)
        return False
    new_w, new_h, left, right, up, down = _minimal_expansion(base_w, base_h, target_w, target_h)
    print(f"Expanding to exact aspect ratio: {new_w}x{new_h} (left={left}, right={right}, up={up}, down={down})")
    if left + right + up + down == 0:
        print("No expansion computed (already handled).")
        input_img.save(output_image_path)
        return False
    _outpaint_image(
        input_image_path=input_image_path,
        output_image_path=output_image_path,
        left=left,
        right=right,
        up=up,
        down=down,
    )
    print(f"✅ Outpainted image saved to {output_image_path}")
    return True
