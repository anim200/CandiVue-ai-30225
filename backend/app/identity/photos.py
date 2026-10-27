"""The face photo sent with the application (F7, §4B-15).

prepare() turns the downloaded file into what CandiVue keeps: the face
embedding (128 numbers) and a small JPEG copy cropped around the face, for
the interviewer's panel. The original file is never stored.

Phone photos need care: they can be HEIC (iPhone), are often very large,
and are stored sideways with a note (EXIF) saying how to turn them. The
type is checked by content, not by the file name.
"""

import io

import cv2
import numpy as np
import pillow_heif
from PIL import Image, ImageOps, UnidentifiedImageError

from app.db.models.interview import PhotoStatus
from app.identity import faces

pillow_heif.register_heif_opener()  # lets Pillow open HEIC/HEIF photos

MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 50_000_000  # refuse "decompression bombs" before decoding
MAX_SIDE = 1600  # larger photos are scaled down first (faster, same result)
THUMBNAIL_SIDE = 320
THUMBNAIL_QUALITY = 85
HEIF_BRANDS = (b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1")
# What the interviewer reads when the photo cannot be used.
TEXTS = {
    PhotoStatus.NO_FACE: "No face could be found in the application photo.",
    PhotoStatus.SEVERAL_FACES: "The application photo shows more than one person.",
    PhotoStatus.TOO_SMALL: "The face in the application photo is too small to compare.",
    PhotoStatus.UNREADABLE: "The application photo is not an image CandiVue can read.",
    PhotoStatus.TOO_LARGE: "The application photo is larger than 10 MB.",
    PhotoStatus.DOWNLOAD_FAILED: "The application photo could not be downloaded yet.",
}


class PhotoError(Exception):
    """The application photo cannot be used; status says why."""

    def __init__(self, status: PhotoStatus):
        super().__init__(TEXTS[status])
        self.status = status


def is_image(data: bytes) -> bool:
    """True for JPEG, PNG, WebP and HEIC/HEIF files (by their first bytes)."""
    return (
        data.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n"))  # JPEG, PNG
        or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")
        or (data[4:8] == b"ftyp" and data[8:12] in HEIF_BRANDS)
    )


def read_photo(data: bytes) -> np.ndarray:
    """The photo as an upright image, at most MAX_SIDE pixels on its longest
    side (BGR pixels, as OpenCV uses them). PhotoError when it is too large
    or not a readable image."""
    if len(data) > MAX_PHOTO_BYTES:
        raise PhotoError(PhotoStatus.TOO_LARGE)
    if not is_image(data):
        raise PhotoError(PhotoStatus.UNREADABLE)
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > MAX_PIXELS:
                raise PhotoError(PhotoStatus.TOO_LARGE)
            upright = ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise PhotoError(PhotoStatus.UNREADABLE) from None
    upright.thumbnail((MAX_SIDE, MAX_SIDE))
    return cv2.cvtColor(np.asarray(upright), cv2.COLOR_RGB2BGR)


def prepare(data: bytes) -> tuple[np.ndarray, bytes]:
    """The face embedding and a small JPEG copy (cropped around the face)
    of an application photo. PhotoError when it cannot be used."""
    image = read_photo(data)
    try:
        face = faces.find_face(image)
        embedding = faces.face_embedding(image, face)
    except faces.FaceError as exc:
        raise PhotoError(PhotoStatus(exc.reason)) from None
    return embedding, thumbnail(image, face)


def thumbnail(image: np.ndarray, face: np.ndarray) -> bytes:
    """A square JPEG of the face with some space around it, THUMBNAIL_SIDE
    pixels wide."""
    height, width = image.shape[:2]
    x, y, w, h = (float(v) for v in face[:4])
    side = min(max(w, h) * 2.2, width, height)
    left = int(min(max(x + w / 2 - side / 2, 0), width - side))
    top = int(min(max(y + h / 2 - side / 2, 0), height - side))
    crop = image[top : top + int(side), left : left + int(side)]
    small = cv2.resize(
        crop, (THUMBNAIL_SIDE, THUMBNAIL_SIDE), interpolation=cv2.INTER_AREA
    )
    _ok, jpeg = cv2.imencode(
        ".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, THUMBNAIL_QUALITY]
    )
    return jpeg.tobytes()
