"""
Decode a base64 string encoded image to a numpy array (np.ndarray).

Raises ValueError if the base64 string is invalid or the image cannot be decoded.

Handle errors gracefully (invalid base64, corrupt image, etc.)
"""

import base64
import binascii
from io import BytesIO
import numpy as np
from PIL import Image, UnidentifiedImageError #Python imaging library (PIL) for image processing

def decode_base64_image(base64_string: str):
    if not base64_string:
        raise ValueError("No image data provided.")

    try:
        # Handle data URLs from the frontend:
        # data:image/jpeg;base64,/9j/4AAQ...
        if "," in base64_string:
            _, base64_string = base64_string.split(",", 1)

        # Base64 -> raw bytes
        image_bytes = base64.b64decode(
            base64_string,
            validate=True
        )

        # Raw bytes -> PIL image -> RGB
        image = Image.open(BytesIO(image_bytes))
        image = image.convert("RGB")  #convert to RGB so every image has the same number of channels (3), arc_face.py expects RGB images

        # PIL image -> NumPy array
        image_array = np.array(image)

        return image_array

    except (binascii.Error, ValueError, UnidentifiedImageError) as e:
        raise ValueError("Invalid Base64 image.") from e
