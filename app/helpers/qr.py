import base64
from io import BytesIO

import qrcode


def qr_data_uri(texto):
    img = qrcode.make(texto)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"
