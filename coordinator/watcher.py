import time, os.path, pickle
import logging
import zmq, pyinotify
from optparse import OptionParser
from utils import *

logging.basicConfig(format='%(asctime)s [%(name)s - %(levelname)s] %(message)s', level=logging.DEBUG)
logger = logging.getLogger('coord.watcher')

context = zmq.Context()

TEST_DIR = '/home/trey/node'

class FileModifiedHandler(pyinotify.ProcessEvent):
    def my_init(self, sync, watch_dir, manager, exclude=None):
        self.watch_dir = watch_dir
        self.sync = sync
        self.manager = manager
        self.exclude = exclude
    
    def _excl(self, path):
        #This is a decorator would be grand.
        if self.exclude is None:
            return False
        return self.exclude(path)
    
    def process_IN_DELETE(self, event):
        if self._excl(event.pathname):
            return
        logger.debug('Remove File: %s', event.pathname)
        self.sync.broadcast(command('REMV', strip_local_path(event.pathname, self.watch_dir)))

    def process_IN_CREATE(self, event):
        if self._excl(event.pathname):
            return
        #For Directories only. Files will trigger on write.
        if event.dir is True:
            logger.debug('Creating Directory: %s', event.pathname)
            self.sync.broadcast(command('MKDIR', strip_local_path(event.pathname, self.watch_dir)))

    def process_IN_CLOSE_WRITE(self, event):
        if self._excl(event.pathname):
            return
        logger.debug('Update on Close+Write: %s', event.pathname)
        try:
            self.sync.broadcast(command('RECV', strip_local_path(event.pathname, self.watch_dir), get_file_contents(event.pathname), os.stat(event.pathname)))
        except (IOError, OSError), e:
            logger.error('Exception: %s', event.pathname, exc_info=True)

    def process_IN_MOVED_FROM(self, event):
        if self._excl(event.pathname):
            return
        pass
        #!!!!!!!!!!!!!!!! !!!!!!!!!!!!!!!!! !!!!!!!!!!!!!!!!
        #Everything works except moving files out of watched areas. THIS WILL NOT SYNC
        #You would need a pending delete queue and whitelisting function in MOVED_TO

        #When files are moved OUT of the watched area, it's essentially a delete.
        #print event
        #print event.__dict__
        #logger.debug('Moved File From: %s', event.pathname)
        #self.process_IN_DELETE(event)

    def process_IN_MOVED_TO(self, event):
        if self._excl(event.pathname):
            return
        try:
            if event.src_pathname:
                logging.debug('Moved file from %s to %s', event.src_pathname, event.pathname)
                self.sync.broadcast(command('MOVE', 
                                            strip_local_path(event.src_pathname, self.watch_dir),
                                            strip_local_path(event.pathname, self.watch_dir)))
                return
        except AttributeError:
            pass
        
        logging.debug('Moved file to %s with unknown source, creating.', event.pathname)
        try:
            if event.dir is True:
                #Get client to request all files in the dir.
                self.sync.broadcast(command('LIST', 
                                            list(generate_file_paths(generate_file_hash(generate_file_tree(event.pathname)), self.watch_dir))
                                            ))
            else:
                #Push one file through.
                self.sync.broadcast(command('RECV', 
                                            strip_local_path(event.pathname, self.watch_dir), 
                                            get_file_contents(event.pathname), 
                                            os.stat(event.pathname)))
        except (IOError, OSError), e:
            logger.error('Exception: %s', event.pathname, exc_info=True)
        
    def process_IN_ATTRIB(self, event):
        if self._excl(event.pathname):
            return
        logger.debug('Attrs Changed: %s', event.pathname)
        try:
            self.sync.broadcast(command('META', strip_local_path(event.pathname, self.watch_dir), os.stat(event.pathname)))
        except (IOError, OSError), e:
            logger.error('Exception: %s', event.pathname, exc_info=True)
    
    def process_IN_MOVE_SELF(self, event):
        if self._excl(event.pathname):
            return
        #A watched directory has moved.
        logger.debug('Watch %s updated for: %s', event.wd, event.pathname)
        self.manager.update_watch(event.wd, rec=True)
    
    def process_default(self, event):
        logger.warning('Unhandled Event: %s:%s', event.maskname, event.pathname)


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
        logger.info('Sync Request, Generating List...')
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

running = True
def main():
    #Create option parser.
    parser = OptionParser(usage="usage: %prog [options] DIRECTORY",
                          version="%prog 0.1")
    parser.add_option("-s", "--sync", dest="sync", action="store_true", 
                      default=False, help="Sync on start")
    parser.add_option("-b", "--bind", dest="bind", action="store", 
                      default='*', help="Host to bind to")
    parser.add_option("-p", "--port", dest="port", action="store", 
                      default=7890, help="TCP port to bind to, the port +1 from this port is also used.")
    parser.add_option("-e", "--exclude", dest="exclude", action="store", 
                      default='', help="Exclude this regular expression from processing. (Multiple isn't implemented because the python opt parser sucks sort of.)")
    
    (options, args) = parser.parse_args()

    if len(args) != 1:
        print 'Invalid Usage'
        parser.print_help()
        return
    
    CHROOT_DIR = args[0] #I could probably ACTUALLY USE CHROOT here... save a lot of filename munging
    #os.chroot(CHROOT_DIR) #Needs ROOT
    
    # The watch manager stores the watches and provides operations on watches
    wm = pyinotify.WatchManager()

    sync = FileSync(CHROOT_DIR, host=options.bind, port=options.port)

    #Exclude Filter
    excl = None
    if options.exclude:
        excl = pyinotify.ExcludeFilter([options.exclude])

    notifier = pyinotify.Notifier(wm, FileModifiedHandler(watch_dir=CHROOT_DIR, sync=sync, manager=wm, exclude=excl), timeout=10)
    notifier.coalesce_events()

    # Events that indicate modified files. (MOVED_SELF would be useful, but doesn't seem to work)
    mask = pyinotify.IN_DELETE | pyinotify.IN_CLOSE_WRITE | pyinotify.IN_MOVED_TO | pyinotify.IN_ATTRIB | pyinotify.IN_MOVE_SELF | pyinotify.IN_MOVED_FROM | pyinotify.IN_CREATE
    #mask = pyinotify.ALL_EVENTS
    
    wdd = wm.add_watch(CHROOT_DIR, mask, rec=True, 
                       auto_add=True, 
                       exclude_filter=excl)

    try:
        while running:
            sync.check_messages()
            if notifier.check_events():
                notifier.read_events()
                notifier.process_events()
            #Not necessary because of the pyinotify timeout attribute.
            #time.sleep(0.0100) #Prevent busy loop
    except KeyboardInterrupt:
        logger.info('Keyboard Interrupt, Exiting...')

if __name__ == '__main__':
    main()










