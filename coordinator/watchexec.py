"""
Watch a file or set of files for changes and 
exec an action if they do change.
"""

import sys, os, os.path, time, fnmatch, subprocess
import pyinotify
from functools import partial
from optparse import OptionParser

class IfChangedHandler(pyinotify.ProcessEvent):
    def my_init(self, callback):
        self.callback = callback
    
    def changed(self, filename):
        self.callback(filename)
    
    def process_IN_DELETE(self, event):
        self.changed(event.pathname)
        
    def process_IN_CLOSE_WRITE(self, event):
        self.changed(event.pathname)

#    def process_IN_MOVED_FROM(self, event):
#        self.process_IN_DELETE(event)

    def process_IN_MOVED_TO(self, event):
        self.changed(event.pathname)
    
    def process_IN_ATTRIB(self, event):
        self.changed(event.pathname)


EXEC_NOTICES = {}

def test_notices(callback, debounce=2):
    now = int(time.time())
    for fn, t in EXEC_NOTICES.items():
        if t <= (now - debounce):
            EXEC_NOTICES.pop(fn)
            callback(fn)

def add_notice(filename):
    now = int(time.time())
    EXEC_NOTICES[filename] = now

def watch(watch_dir, callback, recursive=True):
    """
    TODO: Investigate.
    This function is broken. It does not wait for 2 seconds (the debounce 
    value in test_notices) between receiving an event and the execution of 
    the command.
    
    It does however solve my issue which is to coalesce or debounce the events
    that could happen in a rapid fire succession.
    
    I believe the issue comes from the timeout in the notifier and the main loop, 
    I really don't know.
    """
    wm = pyinotify.WatchManager()
    
    notifier = pyinotify.Notifier(wm, IfChangedHandler(callback=add_notice), timeout=100)
    notifier.coalesce_events()
    
    mask = pyinotify.IN_DELETE | pyinotify.IN_CLOSE_WRITE | pyinotify.IN_MOVED_TO | pyinotify.IN_ATTRIB# | pyinotify.IN_MOVED_FROM | pyinotify.IN_MOVE_SELF
    wdd = wm.add_watch(watch_dir, mask, rec=recursive, auto_add=True)
    
    try:
        while True:
            if notifier.check_events():
                notifier.read_events()
                notifier.process_events()
            test_notices(callback)
    except KeyboardInterrupt:
        print 'Exiting...'
    

def run_command(command, watch_filter, filename):
    if not fnmatch.fnmatch(filename, watch_filter):
        return
    new_command = []
    for part in command:
        new_command.append(part.replace('{}', filename))
    subprocess.call(new_command)

def main():
    #Create option parser.
    parser = OptionParser(usage="usage: %prog [options] \"PATTERN\" -- COMMAND",
                          version="%prog 0.1")
    parser.add_option("-d", "--directory", dest="directory", action="store", 
                      default='./', help="The directory to watch, if omitted CWD.")
    parser.add_option("-f", "--filter", dest="filter", action="store", 
                      default='*', help="Filter execs to file changes matching the pattern.")

    (options, args) = parser.parse_args()

    try:
        command = sys.argv[sys.argv.index('--')+1:]
    except ValueError:
        print 'Separate command with --'
        sys.exit(1)
    
    callback = partial(run_command, command, options.filter)
    
    watch(options.directory, callback)

if __name__ == '__main__':
    main()




