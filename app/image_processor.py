import base64
from PIL import Image
import io

def encode_image(image_path, resize_max=1024):
    img = Image.open(image_path).convert("RGB")
    if max(img.size) > resize_max:
        ratio = resize_max / max(img.size)
        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
        img = img.resize(new_size)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")
