"""Serves the ticket PDFs that the mock S3 (dg-tms-api e2e mock_dgepay.py) saved, so the portal's download links work.
Link shape the API builds: <STORAGE_PUBLIC_URL>/<bucket>/<key>; the mock stores <UPLOAD_DIR>/<key>, so the bucket is dropped.
Usage: python mock_media.py <upload_dir> [port=18091]"""
import os, sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class H(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        return super().translate_path("/" + path.partition("?")[0].lstrip("/").partition("/")[2])

    def end_headers(self):  # the portal first tries to fetch the file as a blob (cross-origin)
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


if __name__ == "__main__":
    d = os.path.abspath(sys.argv[1])
    os.makedirs(d, exist_ok=True)
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[2]) if len(sys.argv) > 2 else 18091), partial(H, directory=d)).serve_forever()
