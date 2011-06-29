import os, os.path, time, logging, shutil
import zmq, pickle
from optparse import OptionParser
from utils import *

logging.basicConfig(format='%(asctime)s [%(name)s - %(levelname)s] %(message)s', level=logging.DEBUG)
logger = logging.getLogger('coord.listener')

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
                else:
                    logger.warning('Tried to execute unknown command: %s', command)
            except zmq.ZMQError:
                break

    def send_recv(self, obj):
        self.request.send(pickle.dumps(obj, pickle.HIGHEST_PROTOCOL))
        command, args = pickle.loads(self.request.recv())
        met = getattr(self, 'command_%s' % command, None)
        if met is not None:
            met(*args)
    
    def command_MKDIR(self, filename):
        localname = os.path.join(self.local_chroot, filename)
        if not os.path.isdir(localname):
            logger.debug('Creating Directory "%s"', filename)
            try:
                os.makedirs(localname)
            except OSError:
                logger.error('Exception.', exc_info=True)
    
    def command_RECV(self, filename, content, stat=None):
        logger.debug('Fetching file "%s"', filename)
        localname = os.path.join(self.local_chroot, filename)
        with open(localname, 'wb') as fp:
            fp.write(content)
        if stat is not None:
            self.command_META(filename, stat)

    def command_META(self, filename, stat):
        logger.debug('Updating attributes for "%s"', filename)
        localname = os.path.join(self.local_chroot, filename)
        try:
            os.chmod(localname, stat.st_mode)
            os.utime(localname, (stat.st_atime, stat.st_mtime))
            if os.geteuid() == 0:
                #Can only be done as root
                os.chown(localname, stat.st_uid, stat.st_gid)
            else:
                logger.debug('Skipping chown files %s because not running as root.', filename)
        except OSError, e:
            logger.error('Exception.', exc_info=True)
    
    def command_MOVE(self, fromname, toname):
        logger.debug('Moving from %s to %s', fromname, toname)
        localfrom = os.path.join(self.local_chroot, fromname)
        localto = os.path.join(self.local_chroot, toname)
        if os.path.isdir(localto):
            logger.debug('Destination is a directory, removing')
            shutil.rmtree(localto)
        try:
            os.rename(localfrom, localto)
        except OSError, e:
            logger.error('Exception during move.', exc_info=True)
    
    def command_REMV(self, filename):
        logger.debug('Removing %s', filename)

        localname = os.path.join(self.local_chroot, filename)
        if os.path.isfile(localname):
            os.remove(localname)
        elif os.path.isdir(localname):
            shutil.rmtree(localname)
        else:
            logger.warning('File %s already gone.', localname)

    def command_LIST(self, file_list):
        # I would rate this algorithm as shit... it could be improved massively.
        logger.debug('Received Synchornization List, Processing...')

        local_files = dict(generate_file_paths(generate_file_hash(generate_file_tree(self.local_chroot)), self.local_chroot))

        #First let's check or remove local files.
        for f, local_stats in local_files.items():
            if f in file_list:
                if f.endswith('/'):
                    #A directory, just make sure it exists.
                    self.command_MKDIR(f)
                else:
                    local_md5, local_stat = local_stats
                    remote_md5, remote_stat = file_list[f]
                    #Local file is in file list.
                    if local_md5 != remote_md5:
                        #Update file
                        self.send_recv(command('SEND', f, True))
                    if compare_file_stat(local_stat, remote_stat) is False:
                        self.command_META(f, remote_stat)
                #Remove from processing list.
                del file_list[f]
            else:
                #File isn't in remote, remove it.
                self.command_REMV(f)

        #Sync remaining files.
        for f, stats in file_list.items():
            self.send_recv(command('SEND', f, True))

#            localname = os.path.join(self.local_chroot, f)
#
#            #Check if dir exists, if it does remove it, if it doesn't create it.
#            dirname = os.path.dirname(localname)
#            if os.path.exists(dirname):
#                logger.debug('Purge for Directory %s', dirname)
#                #shutil.rmtree(localname)
#            logger.debug('Create for Directory %s', dirname)
#            os.makedirs(dirname)
#
#            #Check if file exists
#            if os.path.exists(localname):
#                #If MD5 is identical
#                if md5 == calculate_md5(localname):
#                    continue
#                localstat = os.stat(localname)
#                if localstat != stat:
#                    self.command_META(f, stat)
#            #Update
#            self.send_recv(command('SEND', f))
        logger.debug('Sync Done.')


def main():
    #Create option parser.
    parser = OptionParser(usage="usage: %prog [options] DIRECTORY",
                          version="%prog 0.1")
    parser.add_option("-s", "--sync", dest="sync", action="store_true", 
                      default=False, help="Sync on start")
    #parser.add_option("-d", "--delete", dest="sync", action="store_true",
    #                  default=True, help="Delete local files that aren't on remote.")
    parser.add_option("-b", "--bind", dest="bind", action="store", 
                      default='*', help="Host to bind to")
    parser.add_option("-p", "--port", dest="port", action="store", 
                      default=7890, help="TCP port to bind to, the port +1 from this port is also used.")

    (options, args) = parser.parse_args()
    
    if len(args) != 1:
        print 'Invalid Usage'
        parser.print_help()
        return

    CHROOT_DIR = os.path.abspath(args[0])
    writer = FileWriter(CHROOT_DIR, host=options.bind, port=options.port)

    try:
        if options.sync:
            logger.debug('Requesting Synchronization, Please Wait...')
            writer.start_sync()

        while True:
            writer.recv_broadcast()
            time.sleep(0.0100) #Prevent busy loop
    except KeyboardInterrupt:
        logger.info('Keyboard Interrupt, Exiting...')

if __name__ == '__main__':
    main()