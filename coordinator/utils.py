import os, os.path
import xmlrpclib, httplib, socket
from hashlib import md5

BUFFER_SIZE = 8192

def command(name, *a):
    return [name, a]

def get_file_contents(filename):
    with open(filename, 'rb') as fp:
        return fp.read()

def get_file_stats(filename):
    return os.stat(filename)

def calculate_md5(filename):
    m = md5()
    with open(filename, 'rb') as fp:
        s = fp.read(BUFFER_SIZE)
        while s:
            m.update(s)
            s = fp.read(BUFFER_SIZE)
    hex_md5 = m.hexdigest()
    return hex_md5

def strip_local_path(filename, path):
    filename = filename[len(path):]
    if filename.startswith('/'):
        filename = filename[1:]
    return filename

def generate_file_tree(top):
    #Generate file tree relative to top dir.
    for path, dirlist, filelist in os.walk(top):
        for f in filelist:
            yield os.path.join(path, f)

def generate_file_hash(files):
    for f in files:
        yield f, calculate_md5(f), get_file_stats(f)

def generate_file_paths(tuples, top_dir):
    for path, md5, stat in tuples:
        yield strip_local_path(path, top_dir), md5, stat


#The following skullduggery are two classes are to simulate an HTTP connection through a local socket.
class UnixStreamHTTPConnection(httplib.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        # we abuse the host parameter as the socketname
        self.sock.connect(self.socketfile)

class UnixSocketTransport(xmlrpclib.Transport):
    """
    Provides a Transport for xmlrpclib that uses
    httplib.HTTPConnection in order to support persistent
    connections.  Also support basic auth and UNIX domain socket
    servers.
    """
    connection = None
    _use_datetime = 0 # python 2.5 fwd compatibility
    def __init__(self, serverurl=None):
        self.serverurl = serverurl

    def _get_connection(self, serverurl):
        # we use 'localhost' here because domain names must be
        # < 64 chars (or we'd use the serverurl filename)
        conn = UnixStreamHTTPConnection('localhost')
        conn.socketfile = serverurl[7:]
        return conn

    def request(self, host, handler, request_body, verbose=0):
        if not self.connection:
            self.connection = self._get_connection(self.serverurl)
            self.headers = {
                "User-Agent" : self.user_agent,
                "Content-Type" : "text/xml",
                "Accept": "text/xml"
                }
            
        self.headers["Content-Length"] = str(len(request_body))
        self.connection.request('POST', handler, request_body, self.headers)

        r = self.connection.getresponse()

        if r.status != 200:
            self.connection.close()
            self.connection = None
            raise xmlrpclib.ProtocolError(host + handler,
                                          r.status,
                                          r.reason,
                                          '' )
        data = r.read()
        p, u = self.getparser()
        p.feed(data)
        p.close()
        return u.close()