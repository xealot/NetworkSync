import time, os.path, pickle
import zmq, pyinotify
from optparse import OptionParser
from utils import *

context = zmq.Context()

TEST_DIR = '/home/trey/node'

class FileModifiedHandler(pyinotify.ProcessEvent):
    def my_init(self, sync, watch_dir):
        self.watch_dir = watch_dir
        self.sync = sync
        
    def process_IN_DELETE(self, event):
        #Issue file delete.
        print 'Remove File', event.pathname
        self.sync.broadcast(command('REMV', strip_local_path(event.pathname, self.watch_dir)))

    def process_IN_MOVED_FROM(self, event):
        self.process_IN_DELETE(event)

    def process_IN_CLOSE_WRITE(self, event):
        #Update file
        print 'Update File', event.pathname
        self.sync.broadcast(command('RECV', strip_local_path(event.pathname, self.watch_dir), get_file_contents(event.pathname), os.stat(event.pathname)))

    def process_IN_MOVED_TO(self, event):
        self.process_IN_CLOSE_WRITE(event)
    
    def process_IN_ATTRIB(self, event):
        print 'Change Meta of File', event.pathname
        self.sync.broadcast(command('META', strip_local_path(event.pathname, self.watch_dir), os.stat(event.pathname)))
    
    def process_default(self, event):
        print "%s:%s" % (event.maskname, event.pathname)


class FileSync(object):
    def __init__(self, watch_dir, host='*', port=7890):
        self.watch_dir = watch_dir
        self.publisher = context.socket(zmq.PUB)
        self.publisher.bind('tcp://%s:%s' % (host, port))
        
        self.request = context.socket(zmq.REP)
        self.request.bind('tcp://%s:%s' % (host, port+1))
    
    def broadcast(self, command):
        self.publisher.send(pickle.dumps(command, pickle.HIGHEST_PROTOCOL))
    
    def command_SYNC(self):
        #Gather all files and hashes
        return command('LIST', list(generate_file_paths(generate_file_hash(generate_file_tree(self.watch_dir)), self.watch_dir)))
    
    def command_SEND(self, filename):
        localname = os.path.join(self.watch_dir, filename)
        with open(localname, 'rb') as fp:
            cmd = command('RECV', filename, fp.read())
        return cmd
    
    def check_messages(self):
        while True:
            try:
                msg = self.request.recv(zmq.NOBLOCK)
                command, args = pickle.loads(msg)
                met = getattr(self, 'command_%s' % command, None)
                if met is not None:
                    self.request.send(pickle.dumps(met(*args), pickle.HIGHEST_PROTOCOL))
            except zmq.ZMQError:
                break


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

    CHROOT_DIR = args[0] #I could probably ACTUALLY USE CHROOT here... save a lot of filename munging
    #os.chroot(CHROOT_DIR) #Needs ROOT
    
    # The watch manager stores the watches and provides operations on watches
    wm = pyinotify.WatchManager()

    sync = FileSync(CHROOT_DIR, host=options.bind, port=options.port)

    notifier = pyinotify.Notifier(wm, FileModifiedHandler(watch_dir=CHROOT_DIR, sync=sync), timeout=10)
    notifier.coalesce_events()

    # Events that indicate modified files. (MOVED_SELF would be useful, but doesn't seem to work)
    mask = pyinotify.IN_DELETE | pyinotify.IN_CLOSE_WRITE | pyinotify.IN_MOVED_FROM | pyinotify.IN_MOVED_TO | pyinotify.IN_ATTRIB# | pyinotify.IN_MOVE_SELF
    #mask = pyinotify.ALL_EVENTS
    wdd = wm.add_watch(CHROOT_DIR, mask, rec=True, auto_add=True)

    try:
        while True:
            sync.check_messages()
            if notifier.check_events():
                notifier.read_events()
                notifier.process_events()
    except KeyboardInterrupt:
        print 'Exiting...'












