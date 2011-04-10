import os, os.path, time
import zmq, pickle
from optparse import OptionParser
from utils import *

context = zmq.Context()

CHROOT = './tmp'

class FileWriter(object):
    def __init__(self, local_chroot, host='localhost', port=7890):
        self.local_chroot = local_chroot
        self.subscriber = context.socket(zmq.SUB)
        self.subscriber.connect('tcp://%s:%s' % (host, port))
        self.subscriber.setsockopt(zmq.SUBSCRIBE, '')
        
        self.request = context.socket(zmq.REQ)
        self.request.connect('tcp://%s:%s' % (host, port+1))

    def start_sync(self):
        self.send_recv(command('SYNC'))

    def recv_broadcast(self):
        while True:
            try:
                msg = self.subscriber.recv(zmq.NOBLOCK)
                command, args = pickle.loads(msg)
                met = getattr(self, 'command_%s' % command, None)
                if met is not None:
                    met(*args)
            except zmq.ZMQError:
                break

    def send_recv(self, obj):
        self.request.send(pickle.dumps(obj, pickle.HIGHEST_PROTOCOL))
        command, args = pickle.loads(self.request.recv())
        met = getattr(self, 'command_%s' % command, None)
        if met is not None:
            met(*args)
    
    def command_RECV(self, filename, content, stat=None):
        localname = os.path.join(self.local_chroot, filename)
        print 'Updating %s' % localname
        with open(localname, 'wb') as fp:
            fp.write(content)
        if stat is not None:
            self.command_META(filename, stat)

    def command_META(self, filename, stat):
        localname = os.path.join(self.local_chroot, filename)
        print "Fixing Attribs for %s" % localname
        try:
            os.chmod(localname, stat.st_mode)
            os.utime(localname, (stat.st_atime, stat.st_mtime))
            if os.geteuid() == 0:
                #Can only be done as root
                os.chown(localname, stat.st_uid, stat.st_gid)
        except OSError, e:
            print "Failed with OSERROR %s" % str(e)

    def command_REMV(self, filename):
        localname = os.path.join(self.local_chroot, filename)
        print 'Removing %s' % localname
        os.remove(localname)

    def command_LIST(self, file_list):
        for f, md5 in file_list:
            localname = os.path.join(self.local_chroot, f)
            #Check if file exists
            if os.path.exists(localname):
                #If MD5 is identical
                if md5 == calculate_md5(localname):
                    continue
            #Check at least dir exists
            dirname = os.path.dirname(localname)
            if not os.path.exists(dirname):
                print 'Creating Directory %s' % dirname
                os.makedirs(dirname)
            #Update
            self.send_recv(command('SEND', f))
        print 'Sync Done.'


if __name__ == '__main__':
    #Create option parser.
    parser = OptionParser(usage="usage: %prog [options] DIRECTORY",
                          version="%prog 0.1")
    parser.add_option("-s", "--sync", dest="sync", action="store_true", 
                      default=False, help="Sync on start")
    parser.add_option("-b", "--bind", dest="bind", action="store", 
                      default='*', help="Host to bind to")
    parser.add_option("-p", "--port", dest="port", action="store", 
                      default=7890, help="TCP port to bind to, the port +1 from this port is also used.")

    (options, args) = parser.parse_args()
    
    CHROOT_DIR = args[0]
    writer = FileWriter(CHROOT_DIR, host=options.bind, port=options.port)

    try:
        if options.sync:
            print 'Synchronization, Please Wait...'
            writer.start_sync()

        while True:
            writer.recv_broadcast()
    except KeyboardInterrupt:
        print 'Exiting...'

