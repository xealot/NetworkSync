"""
Monitor application files and restart apps and regenerate 
configs when things change.

If app.yml changes, we need to generate the config and reload nginx.
Touching the yml file should be enough to signify a reload of all stateful 
services.
###If any python files change, we need to HUP the FCGI service.

Our input is a file that was modified.
"""
import subprocess
from optparse import OptionParser

def main(filename):
    subprocess.call(['python', 'deploy.py', '-f %s' % filename])

if __name__ == '__main__':
    #Create option parser.
    parser = OptionParser(usage="usage: %prog FILE",
                          version="%prog 0.1")

    (options, args) = parser.parse_args()
    if len(args) < 1:
        print 'Invalid Usage, check -h'
        sys.exit(1)

    main(args[0])