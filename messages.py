"""Validate browser attachments and construct Claude's native image content blocks."""
import base64
import binascii

MAX_IMAGE = 4 * 1024 * 1024
MAX_TOTAL = 12 * 1024 * 1024
MAX_IMAGES = 4
REQUEST_LIMIT = 18 * 1024 * 1024  # base64 expansion plus text/JSON
TYPES = {'image/png', 'image/jpeg', 'image/gif', 'image/webp'}


def image_source(source):
    if not isinstance(source, dict) or source.get('type') != 'base64' or source.get('media_type') not in TYPES:
        raise ValueError('Paste a PNG, JPEG, GIF or WebP image.')
    data = source.get('data')
    if not isinstance(data, str) or len(data) > (MAX_IMAGE + 2) // 3 * 4:
        raise ValueError('Each image must be at most 4 MB.')
    try:
        raw = base64.b64decode(data, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('Invalid image data.')
    mime = source['media_type']
    valid = (mime == 'image/png' and raw.startswith(b'\x89PNG\r\n\x1a\n') or
             mime == 'image/jpeg' and raw.startswith(b'\xff\xd8\xff') or
             mime == 'image/gif' and raw[:6] in (b'GIF87a', b'GIF89a') or
             mime == 'image/webp' and raw[:4] == b'RIFF' and raw[8:12] == b'WEBP')
    if not valid or len(raw) > MAX_IMAGE:
        raise ValueError('The image data does not match its supported format, or exceeds 4 MB.')
    return {'type':'base64', 'media_type':mime, 'data':data}, len(raw)


def message(body, allow_empty=False):
    if not isinstance(body, dict) or not isinstance(body.get('text', ''), str):
        raise ValueError('Invalid message.')
    text, images = body.get('text', '').strip(), body.get('images', [])
    if len(text) > 100000 or not isinstance(images, list) or len(images) > MAX_IMAGES:
        raise ValueError('Messages support up to four images and 100,000 text characters.')
    if not images:
        if not text and not allow_empty:
            raise ValueError('Nothing to send.')
        return text
    blocks, total = [], 0
    for image in images:
        source, size = image_source(image)
        total += size
        blocks.append({'type':'image', 'source':source})
    if total > MAX_TOTAL:
        raise ValueError('Images must total at most 12 MB.')
    if text:
        blocks.append({'type':'text', 'text':text})
    return blocks


def combine(messages):
    if all(isinstance(m, str) for m in messages):
        return '\n\n'.join(messages)
    blocks = []
    for m in messages:
        blocks.extend([{'type':'text', 'text':m}] if isinstance(m, str) else m)
    return blocks
