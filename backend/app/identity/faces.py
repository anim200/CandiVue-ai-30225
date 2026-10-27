"""Face detection and recognition (F7) with two small open models from the
OpenCV Model Zoo, run locally on the CPU (nothing leaves the machine):

- YuNet finds the faces in a picture (MIT licence);
- SFace turns one face into an embedding: 128 numbers. Two pictures of the
  same person give embeddings with a high cosine similarity (Apache 2.0).

Camera pictures are processed in memory and never saved (N16); of the
application photo only a small encrypted copy is kept (photos.py). The models are
downloaded into the image when it is built (backend Dockerfile).
"""

import threading
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from app.core.config import get_settings

DETECTOR_FILE = "face_detection_yunet_2023mar.onnx"
RECOGNIZER_FILE = "face_recognition_sface_2021dec.onnx"
MIN_DETECTION_SCORE = 0.8  # how sure YuNet must be that it is a face
MIN_FACE_PIXELS = 64  # smaller faces are too blurry to compare
MIN_BRIGHTNESS = 45  # mean grey level (0-255) of the face; darker is too dark
PROBLEMS = {
    "unreadable": "The picture could not be read. Please try again.",
    "no_face": "No face found: look at the camera, with your face in good light.",
    "several_faces": "More than one face is in view: make sure only you are in the picture.",
    "too_small": "Your face is too far from the camera: please move closer.",
    "too_dark": "The picture is too dark: please turn on a light or face a window.",
}

# The OpenCV models are not safe to use from two threads at once.
_lock = threading.Lock()


class FaceError(Exception):
    """A picture has no usable face. reason: a PROBLEMS key; the message is
    safe to show."""

    def __init__(self, reason: str):
        super().__init__(PROBLEMS[reason])
        self.reason = reason


def decode_image(data: bytes) -> np.ndarray:
    """A JPEG or PNG file as an image (BGR pixels, as OpenCV uses them)."""
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise FaceError("unreadable")
    return image


def find_face(image: np.ndarray) -> np.ndarray:
    """The one face in the picture as YuNet sees it (x, y, width, height,
    five landmarks, score). FaceError when there is none, more than one, or
    it is too small."""
    with _lock:
        detector, _recognizer = _models()
        height, width = image.shape[:2]
        detector.setInputSize((width, height))
        _found, faces = detector.detect(image)
    if faces is None or len(faces) == 0:
        raise FaceError("no_face")
    if len(faces) > 1:
        raise FaceError("several_faces")
    face = faces[0]
    if min(face[2], face[3]) < MIN_FACE_PIXELS:
        raise FaceError("too_small")
    return face


def face_embedding(image: np.ndarray, face: np.ndarray | None = None) -> np.ndarray:
    """The embedding of the one face in the picture (length 1, so a dot
    product is the cosine similarity). FaceError when there is no usable
    face or more than one."""
    if face is None:
        face = find_face(image)
    with _lock:
        _detector, recognizer = _models()
        vector = recognizer.feature(recognizer.alignCrop(image, face)).flatten()
    return vector.astype(np.float32) / np.linalg.norm(vector)


def check_light(image: np.ndarray, face: np.ndarray) -> None:
    """FaceError("too_dark") when the face itself is too dark to compare
    (a camera picture in a dim room)."""
    x, y, w, h = (max(0, int(v)) for v in face[:4])
    grey = cv2.cvtColor(image[y : y + h, x : x + w], cv2.COLOR_BGR2GRAY)
    if grey.size and float(grey.mean()) < MIN_BRIGHTNESS:
        raise FaceError("too_dark")


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity of two embeddings: about 1 for the same face."""
    return float(np.dot(a, b))


@lru_cache(maxsize=1)
def _models():
    """Load the two models once (about 40 MB)."""
    folder = Path(get_settings().face_model_dir)
    detector = cv2.FaceDetectorYN.create(
        str(folder / DETECTOR_FILE), "", (320, 320), MIN_DETECTION_SCORE
    )
    recognizer = cv2.FaceRecognizerSF.create(str(folder / RECOGNIZER_FILE), "")
    return detector, recognizer
