"""
Unit tests: contributor uploads are size-capped before parsing and streamed to a
disk temp file instead of being read into memory (PL-060).
"""

import asyncio
import hashlib
import io
import tempfile

import pytest
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from src.api.app import app
from src.api.middleware import UploadSizeLimitMiddleware
from src.api.routes import contributor
from src.main import use_disk_tempdir

UPLOAD_URL = "/api/v1/contributor/upload/fam"


def _small_app(limit: int) -> tuple[FastAPI, list]:
    """A tiny app with the limiter in front of one upload route; records handler calls."""
    calls = []
    small = FastAPI()
    small.add_middleware(UploadSizeLimitMiddleware, path_prefix="/up/", max_body_bytes=limit)

    @small.post("/up/x")
    async def up(file: UploadFile = File(...)):
        calls.append(file.filename)
        return {"ok": True}

    @small.post("/other")
    async def other(file: UploadFile = File(...)):
        return {"ok": True}

    return small, calls


class TestUploadSizeLimitMiddleware:
    """Oversized bodies are refused before the route runs."""

    def test_declared_length_over_cap_rejected(self):
        """The real app refuses a too-large Content-Length without reading the body."""
        limit = contributor.MAX_UPLOAD_BYTES + 1024 * 1024
        response = TestClient(app).post(
            UPLOAD_URL,
            content=b"x",
            headers={"Content-Length": str(limit + 1), "Content-Type": "multipart/form-data; boundary=b"},
        )
        assert response.status_code == 413
        assert "too large" in response.json()["detail"].lower()

    def test_small_upload_passes(self):
        small, calls = _small_app(limit=10_000)
        response = TestClient(small).post("/up/x", files={"file": ("p.jpg", b"tiny", "image/jpeg")})
        assert response.status_code == 200
        assert calls == ["p.jpg"]

    def test_over_cap_with_length_never_reaches_route(self):
        small, calls = _small_app(limit=100)
        response = TestClient(small).post("/up/x", files={"file": ("p.jpg", b"x" * 500, "image/jpeg")})
        assert response.status_code == 413
        assert calls == []

    def test_chunked_body_over_cap_rejected(self):
        """No Content-Length: bytes are counted as they arrive."""
        small, calls = _small_app(limit=100)
        boundary = "b0undary"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"p.jpg\"\r\n"
            f"Content-Type: image/jpeg\r\n\r\n".encode()
            + b"x" * 500
            + f"\r\n--{boundary}--\r\n".encode()
        )

        def chunks():
            for i in range(0, len(body), 64):
                yield body[i:i + 64]

        response = TestClient(small).post(
            "/up/x", content=chunks(), headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        assert response.status_code == 413
        assert calls == []

    def test_other_paths_not_limited(self):
        small, _ = _small_app(limit=100)
        response = TestClient(small).post("/other", files={"file": ("p.jpg", b"x" * 500, "image/jpeg")})
        assert response.status_code == 200


def _upload_file(data: bytes) -> UploadFile:
    return UploadFile(io.BytesIO(data), filename="p.jpg", headers=Headers({"content-type": "image/jpeg"}))


class TestSpoolUpload:
    """The route's chunked copy to a temp file."""

    @pytest.fixture(autouse=True)
    def temp_in_tmp_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
        self.tmp_path = tmp_path

    def test_returns_size_and_md5(self, monkeypatch):
        monkeypatch.setattr(contributor, "_CHUNK_BYTES", 7)  # force several chunks
        data = b"0123456789" * 10
        path, size, digest = asyncio.run(contributor._spool_upload(_upload_file(data), ".jpg"))
        assert path.parent == self.tmp_path
        assert path.read_bytes() == data
        assert size == len(data)
        assert digest == hashlib.md5(data).hexdigest()

    def test_over_limit_raises_413_and_leaves_no_file(self, monkeypatch):
        monkeypatch.setattr(contributor, "MAX_UPLOAD_BYTES", 50)
        monkeypatch.setattr(contributor, "_CHUNK_BYTES", 16)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(contributor._spool_upload(_upload_file(b"x" * 100), ".jpg"))
        assert exc.value.status_code == 413
        assert list(self.tmp_path.iterdir()) == []


class TestUseDiskTempdir:
    """API startup points tempfile at a private directory on disk."""

    def test_creates_private_dir_and_clears_stale_uploads(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tempfile, "tempdir", None)
        target = tmp_path / "picframe_data" / "tmp"
        target.mkdir(parents=True)
        (target / "picframe_upload_old.jpg").write_bytes(b"x")
        (target / "keep.txt").write_bytes(b"x")

        use_disk_tempdir(target)

        assert tempfile.tempdir == str(target)
        assert (target.stat().st_mode & 0o777) == 0o700
        assert not (target / "picframe_upload_old.jpg").exists()
        assert (target / "keep.txt").exists()

    def test_unusable_dir_keeps_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tempfile, "tempdir", None)
        blocker = tmp_path / "file"
        blocker.write_bytes(b"x")

        use_disk_tempdir(blocker / "tmp")

        assert tempfile.tempdir is None
