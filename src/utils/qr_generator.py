"""
PicFrame 4.0 - QR Code Generator.

Generates QR codes for device pairing.
"""

import base64
import io
import json
from typing import Optional

import qrcode
from qrcode.image.pure import PyPNGImage


def generate_pairing_qr(
    url: str,
    code: str,
    frame_name: str,
    size: int = 10,
) -> str:
    """
    Generate a pairing QR code as base64 PNG.

    The QR code contains JSON data with:
    - url: Tailscale Funnel URL for the frame
    - code: Pairing code
    - name: Frame name

    Args:
        url: Frame's Funnel URL (e.g., "https://frame.tail1234.ts.net")
        code: Pairing code (e.g., "A3B-X7K")
        frame_name: Human-readable frame name
        size: QR code box size (default 10)

    Returns:
        Base64-encoded PNG image
    """
    # Create JSON payload
    payload = json.dumps({
        "url": url,
        "code": code,
        "name": frame_name,
    })

    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=size,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)

    # Create image
    img = qr.make_image(fill_color="black", back_color="white", image_factory=PyPNGImage)

    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer)
    buffer.seek(0)

    return base64.b64encode(buffer.read()).decode("utf-8")


def generate_qr_data_url(
    url: str,
    code: str,
    frame_name: str,
) -> str:
    """
    Generate a pairing QR code as a data URL.

    Suitable for embedding directly in HTML img src.

    Args:
        url: Frame's Funnel URL
        code: Pairing code
        frame_name: Frame name

    Returns:
        Data URL (data:image/png;base64,...)
    """
    b64 = generate_pairing_qr(url, code, frame_name)
    return f"data:image/png;base64,{b64}"


def parse_qr_data(data: str) -> Optional[dict]:
    """
    Parse QR code data from a scan.

    Args:
        data: Raw QR code data string

    Returns:
        Parsed dictionary with url, code, name, or None if invalid
    """
    try:
        parsed = json.loads(data)

        # Validate required fields
        if not all(key in parsed for key in ("url", "code", "name")):
            return None

        return {
            "url": parsed["url"],
            "code": parsed["code"],
            "name": parsed["name"],
        }

    except (json.JSONDecodeError, KeyError):
        return None
