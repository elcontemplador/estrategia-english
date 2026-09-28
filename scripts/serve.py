from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import json, os
ROOT=Path(__file__).resolve().parents[1]
PREFIX="/estrategia-english"
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=str(ROOT/"preview"),**kwargs)
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=="/":
            self.send_response(302);self.send_header("Location",PREFIX+"/");self.end_headers();return
        if path==PREFIX:
            self.send_response(302);self.send_header("Location",PREFIX+"/");self.end_headers();return
        if not path.startswith(PREFIX+"/"):
            self.send_error(404);return
        self.path=self.path[len(PREFIX):]
        super().do_GET()
    def log_message(self,*args): pass
server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
address="http://127.0.0.1:"+str(server.server_port)+PREFIX+"/"
(ROOT/"evidence/preview-server.json").write_text(json.dumps({"url":address,"pid":os.getpid(),"port":server.server_port}),encoding="utf-8")
print(address,flush=True)
server.serve_forever()
