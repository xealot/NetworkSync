"""
Generate Deployment files from default hostmap in system 
and any app.yml config files that might be present in those 
folders.
"""
import os, os.path, subprocess , fnmatch, glob, hashlib, itertools, signal
import xmlrpclib
from optparse import OptionParser
from utils import UnixSocketTransport
from parseapp import basic_server, from_app_config, \
    create_supervise_config, NoConfigException

#API_URL = 'http://sandbox.securehomeoffice.com/__/sys/homefolders2'
#rpc = xmlrpclib.ServerProxy('http://iamignored', transport=UnixSocketTransport('unix:///var/run//supervisor.sock'))

SYM_SUPERVISOR = '/mnt/conf/supervisor.d'
SYM_NGINX = '/mnt/conf/nginx.d'
MVH_APPEND = '%s.%s.public.homeplatehq.com'

def reload_nginx():
    command = ['nginx', '-s', 'reload']
    print "Reloading NGINX: %s" % ' '.join(command)
    subprocess.call(command)

def reload_uwsgi():
    pid = None
    try:
        with open('/var/run/uwsgi.pid', 'rb') as fp:
            pid = fp.read()
        os.kill(int(pid), signal.SIGHUP)
        print "Reloading uWSGI Service: %s" % pid
    except OSError:
        pass

def reload_supervisor():
    command = ['supervisorctl', 'update']
    print "Reloading SUPERVISOR: %s" % ' '.join(command)
    subprocess.call(command)

def create_symlink(link, filename):
    if os.path.exists(link):
        if os.path.islink(link):
            link_path = os.readlink(link)
            if os.path.samefile(link_path, filename):
                return
        os.remove(link)
    os.symlink(filename, link)

def deploy_application(conf_dir, node):
    changed_config = False
    #Remove config files before creating them (this is a bad way to work this)
    for fn in glob.glob(os.path.join(conf_dir, '*.nginx')) + glob.glob(os.path.join(conf_dir, '*.supervise')):
        os.remove(fn)

    for server in node:
        server_name = server.attrs.get('name')

        outfile = os.path.join(conf_dir, '%s.nginx' % server_name)
        outcont = server.output()
        write_webconf = True
        if os.path.isfile(outfile):
            with open(outfile, 'r') as fp:
                if hashlib.md5(fp.read()).digest() == hashlib.md5(outcont).digest():
                    write_webconf = False
        
        if write_webconf is True:
            print 'Processing updated %s web server conf into %s' % (server_name, outfile)
            changed_config = True
            with open(outfile, 'w') as fp:
                fp.write(outcont)
        
        create_symlink(os.path.join(SYM_NGINX, '%s.conf' % server_name), outfile)
        
        outfile = os.path.join(conf_dir, '%s.supervise' % server_name)
        if 'spawn' in server.attrs:
            server.attr('socketdir', conf_dir)
            outcont = create_supervise_config(server)
            write_procconf = True
            
            if os.path.isfile(outfile):
                with open(outfile, 'r') as fp:
                    if hashlib.md5(fp.read()).digest() == hashlib.md5(outcont).digest():
                        write_procconf = False
            
            if write_procconf is True:
                print 'Processing updated %s supervise conf into %s' % (server_name, outfile)
                changed_config = True
                with open(outfile, 'w') as fp:
                    fp.write(outcont)
            
            create_symlink(os.path.join(SYM_SUPERVISOR, '%s.conf' % server_name), outfile)
        
        elif os.path.exists(outfile):
            changed_config = True
            os.remove(outfile)
    return changed_config

def build_hostmap(hosts):
    ssl_url = '%s.securenetwork.cc'
    with open(os.path.join('/mnt/conf', 'ssl_canonical.map'), 'w') as fp:
        fp.write('\n'.join(['%s %s;' % (ssl_url % host, canonical) for host, canonical in hosts.items()]))

def scan(locations, app_file='app.yml', skip=None):
    hostmap = {}
    for location in locations:
        if skip is not None and fnmatch.fnmatch(location, skip):
            print 'Skipping "%s" because of skip directive' % location
            continue

        if os.path.isfile(location):
            #Yaml file was specified.
            yml_file = location
            conf_dir = os.path.abspath(os.path.join(os.path.dirname(location), '.config'))
        elif os.path.isdir(location):
            #Directory, YAML file ahould be app_file
            yml_file = os.path.join(location, app_file)
            conf_dir = os.path.abspath(os.path.join(location, '.config'))
        elif not os.path.exists(location):
            print 'Skipping "%s" because it does not exist' % location
            continue
        else:
            print 'Unknown filetype for "%s", skipping' % location
            continue
        
        if not os.path.exists(conf_dir):
            os.makedirs(conf_dir)

        if os.path.isfile(yml_file):
            #If we have a YAML file, build normally.
            print 'Parsing YAML file %s' % yml_file
            node = from_app_config(yml_file, conf_dir, mvh='public.homeplatehq.com')
            for server in node:
                hostmap[server.attrs.get('name')] = server.attrs.get('canonical')
            deploy_application(conf_dir, node=node)
        else:
            #If there is NO yaml file, just make a skeleton static entry.
            print 'NO YAML, Creating Basic Site'
            dirs = location.split('/')
            default_host = MVH_APPEND % (dirs[-1], dirs[-2])

            node = basic_server(location, default_host)
            for server in node:
                hostmap[server.attrs.get('name')] = server.attrs.get('canonical')
            deploy_application(conf_dir, node=node)
    build_hostmap(hostmap)

def main():
    #print rpc.supervisor.getState()
    #Create option parser.
    parser = OptionParser(usage="usage: %prog [options]",
                          version="%prog 0.1")
    parser.add_option("-b", "--base", dest="base", action="store", 
                      help="Base directory for API results if running scan.")
    parser.add_option("-f", "--file", dest="file", action="store", 
                      help="Application YML file")
    parser.add_option("-s", "--skip", dest="skip", action="store", 
                      default=None, help="Skip this pattern from the scan deploy")
    parser.add_option("-r", "--reload", dest="reload", action="store_true", 
                      default=False, help="Reload NGINX configs after running.")
    (options, args) = parser.parse_args()

    #Clean conf dirs.
    print "Purging CONF folders"
    files = glob.glob(os.path.join(SYM_SUPERVISOR, '*.conf')) + glob.glob(os.path.join(SYM_NGINX, '*.conf'))
    for f in files:
        os.remove(f)

    if options.file:
        changed = scan([options.file], skip=options.skip)
    else:
        #When invoked from the shell, this expansion happens automatically... When run from supervisor, the arg is a literal.
        #print list(itertools.chain(*[glob.glob(arg) for arg in args]))
        changed = scan(itertools.chain(*[glob.glob(arg) for arg in args]), skip=options.skip)
    
    if options.reload is True:# and changed: #When things disappear, we'll never hit it...
        print 'Reloading Services'
        reload_nginx()
        reload_supervisor()
        reload_uwsgi()

if __name__ == '__main__':
    main()


