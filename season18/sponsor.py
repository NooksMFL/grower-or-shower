"""Store the original sponsor image without cropping or changing its pixels."""
import base64
from io import BytesIO

from PIL import Image, UnidentifiedImageError

MAX_BYTES = 4 * 1024 * 1024


def validate(content):
    if not isinstance(content, bytes) or not content or len(content) > MAX_BYTES:
        raise ValueError('Choose a PNG, JPG or WebP image smaller than 4 MB.')
    try:
        with Image.open(BytesIO(content)) as image:
            mime = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}.get(image.format)
            if not mime or image.width * image.height > 25000000:
                raise ValueError('Use a PNG, JPG or WebP image up to 25 megapixels.')
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError('The file could not be read as a valid image.') from None
    return mime


def save(store, content):
    mime = validate(content)
    with store.connect() as c:
        c.execute('INSERT OR REPLACE INTO site_assets VALUES(?,?,?)', ('sponsor', mime, content))


def get(store):
    with store.connect() as c:
        row = c.execute("SELECT mime,content FROM site_assets WHERE name='sponsor'").fetchone()
    return {'mime': row[0], 'base64': base64.b64encode(row[1]).decode('ascii')} if row else None


def decode_backup(data):
    if not isinstance(data, dict) or not isinstance(data.get('base64'), str):
        raise ValueError('Invalid sponsor image backup.')
    try:
        content = base64.b64decode(data['base64'], validate=True)
    except ValueError:
        raise ValueError('Invalid sponsor image backup.') from None
    mime = validate(content)
    if mime != data.get('mime'):
        raise ValueError('Invalid image format in backup.')
    return mime, content
