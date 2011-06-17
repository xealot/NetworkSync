"""
Should run this in cron to keep up to date.

* * * * * ubuntu /home/ubuntu/generate_hostmap.py > hosts.map
"""

import urllib2
import simplejson as json
import os, os.path
from optparse import OptionParser

def get_hostmap(api):
    try:
        response = urllib2.urlopen(api)
        api_data = json.loads(response.read())
    except:
        raise
    return api_data

def main(api_data, prefix):
    """
    Output an apache rewrite map based on the domains and their public 
    html directories.
    """
    #Print our default system root first.
    print '%s\t\t%s' % ('base\.public\.homeplatehq\.com', '%s/%s' % (BASEPATH, '.system/public'))
    for i in api_data:
        print '%s\t\t%s' % (i[0], '%s/%s' % (BASEPATH, i[1]))

if __name__ == '__main__':
    #Create option parser.
    parser = OptionParser(usage="usage: %prog [options]",
                          version="%prog 0.1")
    parser.add_option("-a", "--api", dest="api", action="store", 
                      default='http://sandbox.securehomeoffice.com/__/sys/homefolders2', help="API Access Point")
    parser.add_option("-p", "--prefix", dest="bind", action="store", 
                      default='/mnt/repo', help="Directory Prefix")

    (options, args) = parser.parse_args()
    
    print get_hostmap(options.api)
    #main(api_data, options.prefix)