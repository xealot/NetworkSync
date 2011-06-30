import site, os.path
site.addsitedir(os.path.abspath(os.path.join(os.path.dirname(__file__), 'thirdparty')))

import yaml, os, os.path, sys, random
from optparse import OptionParser

class AppConfigException(Exception): pass
class AppConfigException(AppConfigException): pass
class NoConfigException(AppConfigException): pass

class Group(list):
    def output(self, tab=0):
        return '\n'.join([node.output() for node in self])


class Node(object):
    def __init__(self, name, *n, **d):
        self.name = name
        self.arg = d.pop('arg', '')
        self.attrs = {}
        self.chain = list(n)
        self.chain.extend([Directive(k,v) for k,v in d.items()])
    def add(self, *a, **d):
        self.chain.extend(a)
        self.chain.extend([Directive(k,v) for k,v in d.items()])
    def attr(self, n, value):
        self.attrs[n] = value
    def output(self, tab=0):
        return """%(tabs)s%(name)s %(arg)s {\n%(chain)s\n%(tabs)s}""" % {
            'tabs': (' '*tab*2), 
            'name': self.name, 
            'arg': self.arg, 
            'chain': '\n'.join([d.output(tab=tab+1) for d in self.chain])}


class Directive(object):
    def __init__(self, name, value):
        self.name = name
        self.value = value
    def output(self, tab=0):
        return '%s%s %s;' % ((' '*tab*2), self.name, self.value)


class Comment(object):
    def __init__(self, comment):
        self.comment = comment
    def output(self, tab=0):
        return '%s# %s' % ((' '*tab*2), self.comment)

def escape(arg):
    if any(map(lambda x: x in arg, ('-', ' '))):
        return '"%s"' % arg
    return arg

def create_supervise_config(server_node):
    a = server_node.attrs
    return """
[fcgi-program:%(name)s]
process_name=%%(program_name)s_%%(process_num)02d
numprocs=%(procs)s
environment=PYTHONPATH=%(root)s
directory=%(root)s

command=python %(script)s
socket=unix://%(socketdir)s/%%(program_name)s.sock
socket_owner=www-data
socket_mode=0770
user=www-data
group=www-data

;stdout_logfile=%(logdir)s/%%(program_name)s.out
;stdout_logfile_maxbytes=20MB
;stdout_logfile_backups=2
;stderr_logfile=%(logdir)s/%%(program_name)s.err
;stderr_logfile_maxbytes=20MB
;stderr_logfile_backups=2
    """ % dict(name=a.get('name'),
               root=a.get('root_dir'),
               logdir=a.get('log_dir'),
               procs=a['spawn'].get('procs'),
               socketdir=a.get('socketdir'),
               script=a['spawn'].get('script'))

def create_reload_script(server_node):
    a = server_node.attrs
    return """#!/bin/sh
supervisorctl restart %(name)s
""" % dict(name=a.get('name'))

def create_update_script(yml_file):
    return """#!/bin/sh
ngdeploy -f %s
""" % yml_file

def basic_server(folder, host):
    #Create just a basic server{} node with the specified folder and hosts.
    node = Group()
    server = Node('server', 
        Comment('Default server spec for %s' % folder),
        #listen='8080', #TMP
        root=escape(folder),
        server_name=host
    )
    dirs = folder.split('/')
    server.attr('name', '%s-%s' % (dirs[-2], dirs[-1]))
    server.attr('canonical', host)
    node.append(server)
    return node

def from_app_config(config_file, fcgi_socket_dir, mvh=None):
    if not os.path.isfile(config_file):
        raise NoConfigException(config_file)
        
    with open(config_file, 'r') as fp:
        applications = yaml.load(fp.read())
    
    config = Group()

    for app in applications:
        DEFAULT_ROOT = os.path.abspath(os.path.dirname(config_file))
        LOG_DIR = os.path.abspath(os.path.join(DEFAULT_ROOT, app.get('logs', 'log')))
        if not LOG_DIR.startswith(DEFAULT_ROOT):
            raise AppConfigException('Invalid log location specification.')

        site_name = app.get('application', random.randrange(5000, 9999))

        server = Node('server', 
            Comment('Config for %s in %s' % (site_name, config_file)),
            #listen='8080', #TMP
            #Not until rotate is done.
            #access_log=os.path.join(LOG_DIR, 'access.log'),
            #error_log='%s error' % os.path.join(LOG_DIR, 'error.log'),
        )
        
        server.attr('name', site_name)
        server.attr('canonical', '%s.%s' % (site_name, mvh))
        server.attr('log_dir', LOG_DIR)
        server.attr('root_dir', DEFAULT_ROOT)

        if 'port' in app:
            server.add(listen=app.get('port'))

        server_names = []
        if 'hostname' in app:
            server_names.append(app.get('hostname'))

        mvh_setting = app.get('mvh', 'normal')
        if mvh_setting == 'normal' or mvh_setting == 'both':
            server_names.append('%s.%s' % (site_name, mvh))
        if mvh_setting == 'wildcard' or mvh_setting == 'both':
            server_names.append('*.%s.%s' % (site_name, mvh))
        server.add(server_name=' '.join(server_names))

        if 'webroot' in app:
            #Append the root to the real root.
            
            root = os.path.abspath(os.path.join(DEFAULT_ROOT, app.get('webroot')))
            if not root.startswith(DEFAULT_ROOT):
                raise AppConfigException('Invalid root specification.')
            server.add(root=escape(root))
        else:
            server.add(root=escape(DEFAULT_ROOT))


        #Whitelisted Directives
        for key in ('index', 'try_files'):
            if key in app:
                server.add(Directive(key, app.get(key)))

        if app.get('use_ssi', False):
            server.add(ssi='on')
            
        for rewrite in app.get('rewrites', ()):
            server.add(Directive('rewrite', rewrite))
    
        for handler in app.get('handlers', ()):
            if 'url' in handler:
                location = Node('location', arg=handler.get('url'))
                #Whitelisted Directives
                for key in ('index',):
                    if key in handler:
                        location.add(Directive(key, handler.get(key)))
            
                #Can have redirect or static...
                if 'rewrites' in handler:
                    for rewrite in handler.get('rewrites'):
                        location.add(Directive('rewrite', rewrite))
                elif 'static' in handler:
                    location.add(Directive('root', handler.get('static')))
                elif 'runtime' in handler:
                    runtime = handler.get('runtime')
                    
                    if runtime == 'python':
                        #Using uWSGI, all we need is the entry module. Usually a python file.
                        if 'module' not in handler:
                            raise AppConfigException('module directive required for python based handler.')

                        #callable_app = handler.get('module').split(':')
                        #if len(callable_app) == 1:
                        #    callable_app.append('application')

                        unix_socket = '/var/tmp/uwsgi.sock'
                        location.add(
                            Directive('uwsgi_pass', 'unix://%s' % unix_socket),
                            Directive('include', 'uwsgi_params'),
                            Directive('uwsgi_param', 'UWSGI_SCRIPT %s' % escape(handler.get('module'))),
                            #Directive('uwsgi_param', 'UWSGI_MODULE %s' % callable_app[0]),
                            #Directive('uwsgi_param', 'UWSGI_CALLABLE %s' % callable_app[1]),
                            Directive('uwsgi_param', 'UWSGI_CHDIR %s' % escape(DEFAULT_ROOT)),
                        )

                        #Python needs to have a daemon setup (so stupid) that is specific to a wsgi file.
                        #It loads this wsgi application and communicates via an app specfic socket.
                        #server.attr('spawn', dict(
                        #    procs=3,
                        #    script=os.path.join(DEFAULT_ROOT, handler.get('fcgi')),
                        #))
                        #unix_socket = os.path.join(fcgi_socket_dir, '%s.sock' % app.get('application'))
                    elif runtime == 'php':
                        #PHP just needs the script name, all goes through one socket.
                        unix_socket = '/var/run/php-fpm.sock'
                        location.add(
                            Directive('fastcgi_pass', 'unix://%s' % unix_socket),
                            Directive('include', '/etc/nginx/nginx-fastcgi-params'),
                        )
                    else:
                        raise AppConfigException('Unknown runtime: %s' % runtime)

                server.add(location)
        config.append(server)
    return config

if __name__ == '__main__':
    #Create option parser.
    parser = OptionParser(usage="usage: %prog [options] DIR",
                          version="%prog 0.1")
    parser.add_option("-s", "--socket", dest="socket", action="store", 
                      default='/tmp', help="API Access Point")

    (options, args) = parser.parse_args()
    if len(args) < 1:
        print 'Invalid Usage, check -h'
        sys.exit(1)
    config = from_app_config(args[0], options.socket)
    print config.output()
    
    for server in config:
        if 'spawn' in server.attrs:
            #Needs a spawn
            print create_supervise_config(server)





"""
    Directive('fastcgi_pass_header', 'Authorization'),
    Directive('fastcgi_intercept_errors', 'off'),

    Directive('fastcgi_param', 'REQUEST_METHOD $request_method'),
    Directive('fastcgi_param', 'CONTENT_TYPE $content_type'),
    Directive('fastcgi_param', 'CONTENT_LENGTH $content_length'),
    Directive('fastcgi_param', 'PATH_INFO $fastcgi_script_name'),
    Directive('fastcgi_param', 'QUERY_STRING $query_string'),
    
    Directive('fastcgi_param', 'SCRIPT_NAME $fastcgi_script_name'),
    Directive('fastcgi_param', 'SCRIPT_FILENAME $document_root$fastcgi_script_name'),
    Directive('fastcgi_param', 'REQUEST_URI $request_uri'),
    Directive('fastcgi_param', 'DOCUMENT_URI $document_uri'),
    Directive('fastcgi_param', 'DOCUMENT_ROOT $document_root'),
    Directive('fastcgi_param', 'SERVER_PROTOCOL $server_protocol'),

    Directive('fastcgi_param', 'GATEWAY_INTERFACE CGI/1.1'),
    Directive('fastcgi_param', 'SERVER_SOFTWARE nginx/$nginx_version'),

    Directive('fastcgi_param', 'REMOTE_ADDR $remote_addr'),
    Directive('fastcgi_param', 'REMOTE_PORT $remote_port'),
    Directive('fastcgi_param', 'SERVER_ADDR $server_addr'),
    Directive('fastcgi_param', 'SERVER_PORT $http_port'),
    Directive('fastcgi_param', 'SERVER_NAME $hostname'),
"""

