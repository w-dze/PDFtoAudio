import json
import mimetypes
import multiprocessing
import re
import textwrap
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import pyttsx3
from PyPDF2 import PdfReader


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = BASE_DIR / "uploads"
HOST = "127.0.0.1"
PORT = 8000


def speak_text(text):
    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()
    engine.stop()


class PDFAudioPlayer:
    def __init__(self):
        self.pdf_path = None
        self.speech_process = None
        self.thread = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.resume_page_index = 0
        self.resume_chunk_index = 0
        self.state = {
            "status": "idle",
            "message": "Upload a PDF to begin.",
            "fileName": None,
            "page": None,
            "pages": None,
        }

    def set_pdf(self, pdf_path):
        with self.lock:
            if self.thread and self.thread.is_alive():
                self.stop_event.set()
                self._terminate_speech_process()

            self.pdf_path = pdf_path
            self.resume_page_index = 0
            self.resume_chunk_index = 0
            self.state.update(
                {
                    "status": "ready",
                    "message": "PDF uploaded. Press Start when you are ready.",
                    "fileName": pdf_path.name,
                    "page": None,
                    "pages": None,
                }
            )

    def start(self):
        with self.lock:
            if not self.pdf_path:
                return False, "Upload a PDF first."

            if self.thread and self.thread.is_alive():
                return False, "Already reading."

            self.stop_event.clear()
            message = "Starting audio..."
            if self.resume_page_index or self.resume_chunk_index:
                message = f"Resuming page {self.resume_page_index + 1}..."
            self.state.update({"status": "reading", "message": message})
            self.thread = threading.Thread(target=self._read_pdf, daemon=True)
            self.thread.start()
            return True, "Started reading."

    def stop(self):
        with self.lock:
            if self.state["status"] not in {"reading", "stopping"}:
                self.state.update({"status": "ready", "message": "Ready."})
                return True, "Nothing is currently playing."

            self.stop_event.set()
            self.state.update({"status": "stopping", "message": "Stopping audio..."})
            self._terminate_speech_process()
            return True, "Stopping audio."

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def _set_state(self, **updates):
        with self.lock:
            self.state.update(updates)

    def _read_pdf(self):
        try:
            reader = PdfReader(str(self.pdf_path))
            total_pages = len(reader.pages)
            self._set_state(pages=total_pages)

            for page_index in range(self.resume_page_index, total_pages):
                if self.stop_event.is_set():
                    break

                page_number = page_index + 1
                page = reader.pages[page_index]
                text = page.extract_text()
                if not text:
                    self._set_state(
                        page=page_number,
                        message=f"Skipping page {page_number}; no text found.",
                    )
                    self.resume_page_index = page_index + 1
                    self.resume_chunk_index = 0
                    continue

                chunks = self._split_text(text)
                start_chunk_index = self.resume_chunk_index if page_index == self.resume_page_index else 0

                self._set_state(
                    status="reading",
                    page=page_number,
                    message=f"Reading page {page_number} of {total_pages}.",
                )
                for chunk_index in range(start_chunk_index, len(chunks)):
                    if self.stop_event.is_set():
                        break

                    self.resume_page_index = page_index
                    self.resume_chunk_index = chunk_index

                    if not self._speak_chunk(chunks[chunk_index]):
                        break

                    self.resume_chunk_index = chunk_index + 1

                if self.stop_event.is_set():
                    break

                self.resume_page_index = page_index + 1
                self.resume_chunk_index = 0

            if self.stop_event.is_set():
                self._set_state(
                    status="paused",
                    message=f"Paused on page {self.resume_page_index + 1}. Press Start to resume.",
                )
            else:
                self.resume_page_index = 0
                self.resume_chunk_index = 0
                self._set_state(
                    status="finished",
                    page=total_pages,
                    message="Finished reading the PDF.",
                )
        except Exception as exc:
            self._set_state(status="error", message=f"Could not read PDF: {exc}")
        finally:
            with self.lock:
                self._terminate_speech_process()
            self.stop_event.clear()

    def _speak_chunk(self, chunk):
        process = multiprocessing.Process(target=speak_text, args=(chunk,))
        with self.lock:
            self.speech_process = process

        process.start()

        while process.is_alive():
            if self.stop_event.is_set():
                process.terminate()
                process.join(timeout=1)
                return False
            time.sleep(0.05)

        process.join()
        with self.lock:
            if self.speech_process is process:
                self.speech_process = None

        return process.exitcode == 0

    def _terminate_speech_process(self):
        process = self.speech_process
        if process and process.is_alive():
            process.terminate()
            process.join(timeout=1)
        self.speech_process = None

    def _split_text(self, text):
        pieces = []
        for paragraph in re.split(r"\n\s*\n", text):
            paragraph = re.sub(r"\s+", " ", paragraph).strip()
            if not paragraph:
                continue

            pieces.extend(textwrap.wrap(paragraph, width=180, break_long_words=False))

        return pieces


player = PDFAudioPlayer()


class PDFToAudioHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.handle_get(send_body=False)

    def do_GET(self):
        self.handle_get(send_body=True)

    def handle_get(self, send_body):
        if self.path == "/":
            self.serve_file(STATIC_DIR / "index.html", send_body)
            return

        if self.path == "/api/status":
            self.send_json(player.snapshot(), send_body=send_body)
            return

        if self.path.startswith("/static/"):
            relative_path = unquote(self.path.removeprefix("/static/"))
            self.serve_file(STATIC_DIR / relative_path, send_body)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self):
        if self.path == "/api/upload":
            self.handle_upload()
            return

        if self.path == "/api/start":
            ok, message = player.start()
            self.send_json({"ok": ok, "message": message, "state": player.snapshot()})
            return

        if self.path == "/api/stop":
            ok, message = player.stop()
            self.send_json({"ok": ok, "message": message, "state": player.snapshot()})
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def handle_upload(self):
        content_type = self.headers.get("Content-Type", "")
        boundary_match = re.search(r"boundary=(.*)", content_type)
        if not boundary_match:
            self.send_json({"ok": False, "message": "Missing upload boundary."}, 400)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        boundary = boundary_match.group(1).strip('"').encode()
        file_name, file_content = self.extract_pdf_upload(body, boundary)

        if not file_name or not file_content:
            self.send_json({"ok": False, "message": "Choose a PDF file to upload."}, 400)
            return

        if not file_name.lower().endswith(".pdf"):
            self.send_json({"ok": False, "message": "Only PDF files are accepted."}, 400)
            return

        UPLOAD_DIR.mkdir(exist_ok=True)
        safe_name = Path(file_name).name
        stored_path = UPLOAD_DIR / f"{uuid.uuid4().hex}-{safe_name}"
        stored_path.write_bytes(file_content)
        player.set_pdf(stored_path)
        self.send_json({"ok": True, "message": "PDF uploaded.", "state": player.snapshot()})

    def extract_pdf_upload(self, body, boundary):
        marker = b"--" + boundary
        for part in body.split(marker):
            if b"filename=" not in part:
                continue

            header, _, content = part.partition(b"\r\n\r\n")
            if not content:
                continue

            filename_match = re.search(rb'filename="([^"]+)"', header)
            if not filename_match:
                continue

            file_name = filename_match.group(1).decode("utf-8", errors="replace")
            content = content.removesuffix(b"\r\n").removesuffix(b"--")
            return file_name, content

        return None, None

    def serve_file(self, path, send_body=True):
        safe_path = path.resolve()
        if STATIC_DIR.resolve() not in safe_path.parents and safe_path != STATIC_DIR.resolve():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return

        if not safe_path.exists() or not safe_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return

        mime_type = mimetypes.guess_type(safe_path)[0] or "application/octet-stream"
        content = safe_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if send_body:
            self.wfile.write(content)

    def send_json(self, payload, status=200, send_body=True):
        content = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        if send_body:
            self.wfile.write(content)

    def log_message(self, format, *args):
        return


def run_server():
    server = ThreadingHTTPServer((HOST, PORT), PDFToAudioHandler)
    print(f"PDF to Audio is running at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
