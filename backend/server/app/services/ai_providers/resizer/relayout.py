from io import BytesIO
from openai import OpenAI
from PIL import Image
import base64
from app.core.config import settings
from google import genai
from google.genai import types
from typing import Literal, Optional
import mimetypes

# Initialize OpenAI client lazily (only if needed) so that absence of key
# doesn't break usage when another provider is chosen.
_openai_client: Optional[OpenAI] = None
_gemini_client: Optional[genai.Client] = None

def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured but provider 'openai' was requested")
        _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client

def _get_gemini_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not configured but provider 'gemini' was requested")
        _gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _gemini_client

def _run_openai_relayout(input_image_path: str, output_image_path: str, supported_ratio: str, size: str) -> bool:
    """Run the OpenAI image edit relayout. Returns True if successful."""

    openai_prompt = f"""
Take the input image and relayout its elements to fit the target ratio {supported_ratio}.
Keep the content sharp and balanced. Do not crop or distort the original design.
Notes:
- Make sure to preserve the information and content purposes.
- Keep multiline texts readable without distortions.
- Do not add any new components.
- Do not duplicate elements.
- Maintain the original style and color scheme.
- Ensure the final image is well-composed.
"""

    try:
        client = _get_openai_client()
        with open(input_image_path, "rb") as f:
            result = client.images.edit(
                model="gpt-image-1",
                prompt=openai_prompt,
                size=size,
                image=f,
            )
        image_b64 = result.data[0].b64_json
        image_bytes = base64.b64decode(image_b64)
        with open(output_image_path, "wb") as out:
            out.write(image_bytes)
        print(f"✅ OpenAI relayout image saved to {output_image_path}")
        return True
    except Exception as e:
        print(f"OpenAI relayout generation failed: {e}")
        return False

def _run_gemini_relayout(input_image_path: str, output_image_path: str, target_w: int, target_h: int) -> bool:
    """Run the Gemini image relayout. Returns True if successful."""
    if not settings.GEMINI_API_KEY:
        print("GEMINI_API_KEY not configured; skipping Gemini relayout")
        return False

    gemini_prompt = """
Use the second picture as the reference for final aspect ratio and fill the area that wasn't shown in the original picture.
Do not simply stretch, crop, or add background padding. Instead, intelligently re-layout
and reposition all elements (text, logo, product, main subject) so the composition looks
balanced, professional, and natural within the new aspect ratio.
Guidelines:
- Preserve all key elements from the source image (logos, text, products, main visuals).
- Adapt the layout to fully utilize the available space in the placeholder, whether
landscape, portrait, or square.
- Reposition elements if necessary: for example, distribute text and logos into
new areas, shift the main subject off-center, or reorganize hierarchy to match the
target aspect ratio.
- Extend or generate background only as needed to support the new layout.
- The final result must look like a true design created for the new size,
not just the original with empty margins or padding.
- Maintain brand consistency, colors, and style.
- Do not duplicate elements.
"""

    try:
        client_gemini = _get_gemini_client()

        # 1. Read original image
        with open(input_image_path, "rb") as f:
            image_bytes_in = f.read()

        # 2. Create transparent placeholder image
        placeholder = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        placeholder_bytes_io = BytesIO()
        placeholder.save(placeholder_bytes_io, format="PNG")
        placeholder_bytes = placeholder_bytes_io.getvalue()

        # 3. Construct content with two images and a specific prompt
        # Determine the MIME type from the input file path
        mime_type, _ = mimetypes.guess_type(input_image_path)
        if not mime_type or not mime_type.startswith("image/"):
            # Fallback for unknown types, default to PNG
            mime_type = "image/png"

        gemini_contents = [
            types.Content(
            role="user",
            parts=[
                types.Part.from_bytes(mime_type=mime_type, data=image_bytes_in),
                types.Part.from_bytes(mime_type="image/png", data=placeholder_bytes),
                types.Part.from_text(text=gemini_prompt)
            ],
            ),
        ]
        gemini_config = types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        )
        gemini_response = client_gemini.models.generate_content(
            model="gemini-2.5-flash-image-preview",
            contents=gemini_contents,
            config=gemini_config,
        )
    except Exception as e:
        print(f"Gemini relayout generation failed: {e}")
        return False

    if getattr(gemini_response, "candidates", None):
        for cand in gemini_response.candidates or []:
            content = getattr(cand, "content", None)
            if not content:
                continue
            for part in getattr(content, "parts", []) or []:
                inline = getattr(part, "inline_data", None)
                if not (inline and getattr(inline, "data", None)):
                    continue

                print(f"Gemini response contains inline data with mime_type: {inline.mime_type}")
                if "image" not in inline.mime_type:
                    print("Skipping non-image part.")
                    continue

                print("Attempting to process inline image data from Gemini.")
                try:
                    # First, try to open the data directly
                    img = Image.open(BytesIO(inline.data))
                    img.save(output_image_path, "PNG")
                    print(f"✅ Gemini relayout image saved to {output_image_path}")
                    return True  # Success, we are done.
                except Exception as e:
                    print(f"Directly opening image data failed: {e}. Trying base64 decode.")
                    # If that fails, try decoding from base64
                    try:
                        # The data might be a base64 encoded string stored in bytes.
                        decoded_data = base64.b64decode(inline.data)
                        img = Image.open(BytesIO(decoded_data))
                        img.save(output_image_path, "PNG")
                        print(f"✅ Gemini relayout image saved after base64 decode to {output_image_path}")
                        return True
                    except Exception as e2:
                        print(f"Failed processing Gemini image part, even after base64 decode: {e2}")
                        # Continue to the next part
    
    print("Gemini response did not contain any valid inline image data after trying all parts.")
    return False

ProviderType = Literal["openai", "gemini", "fallback", "auto"]

def relayout_if_needed(
    input_image_path: str,
    output_image_path: str,
    target_w: int,
    target_h: int,
    provider: ProviderType = "openai",
):
    """
    input_path: path to the input image
    expected_ratio: tuple (w, h), e.g. (9, 16)
    output_path: path to save the result

    provider options:
      - 'openai': use only OpenAI image edit
      - 'gemini': use only Gemini image generation
      - 'fallback': try OpenAI first, fall back to Gemini if it fails
      - 'auto': currently identical to 'fallback' (reserved for future heuristics)
    Returns True if a relayout was performed (i.e., image modified by a provider) or False if skipped.
    """

    # Calculate aspect ratios
    target_ratio = target_w / target_h
    supported_ratio = "1:1"

    # Select size supported by OpenAI
    # (official options: 1024x1024, 1024x1536, 1536x1024)
    if target_ratio > 1.2:   # landscape
        size = "1536x1024"
        supported_ratio_val = 3/2
        supported_ratio = "3:2"
    elif target_ratio < 0.8: # portrait
        size = "1024x1536"
        supported_ratio_val = 2/3
        supported_ratio = "2:3"
    else:                    # square
        size = "1024x1024"
        supported_ratio_val = 1.0
        supported_ratio = "1:1"

    # Get input image aspect ratio
    input_img = Image.open(input_image_path)
    input_w, input_h = input_img.size
    input_ratio = input_w / input_h

    dist_to_input = abs(target_ratio - input_ratio)
    dist_to_supported = abs(target_ratio - supported_ratio_val)

    # If input is closer to expected than supported, skip relayout
    if dist_to_input < dist_to_supported or input_ratio == target_ratio:
        print(f"Skipping relayout for {input_image_path}: input aspect ratio {input_ratio:.3f} is closer or equal to expected {target_ratio:.3f} than supported {supported_ratio_val:.3f}")
        # Just copy the image to output_path
        input_img.save(output_image_path)
        print(f"Copied {input_image_path} to {output_image_path} without relayout.")
        return False


    print(f"Relayouting {input_image_path} to nearest supported size {size} and aspect ratio {supported_ratio} ({supported_ratio_val:.4f}). Input ratio is {input_ratio:.4f}. Target ratio is {target_ratio:.4f}.")

    performed = False
    chosen_provider = provider
    if provider == "auto":  # placeholder for future heuristics
        chosen_provider = "fallback"

    if chosen_provider == "openai":
        performed = _run_openai_relayout(input_image_path, output_image_path, supported_ratio, size)
    elif chosen_provider == "gemini":
        performed = _run_gemini_relayout(input_image_path, output_image_path, target_w, target_h)
    elif chosen_provider == "fallback":
        performed = _run_openai_relayout(input_image_path, output_image_path, supported_ratio, size)
        if not performed:
            print("Falling back to Gemini provider...")
            performed = _run_gemini_relayout(input_image_path, output_image_path, target_w, target_h)
    else:
        raise ValueError(f"Unsupported provider option: {provider}")

    if performed:
        print(f"✅ Generated {output_image_path} (provider workflow: {provider})")
    else:
        print(f"❌ No relayout image generated for provider option '{provider}'.")
    return performed