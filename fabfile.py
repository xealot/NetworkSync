import time, hmac, sha, base64, urllib
import boto.ec2.connection
import functools
import fabric.colors
from fabric.api import *
#from fabric.contrib.console import confirm

AWSKEY = 'AKIAIXAJIJUCEDSI3X5Q'
AWSPAS = '+g84PSYYr1zr2zXMYjNvtDw5ypykNTPlrmGvBDsF'

def _get_ec2_hostnames(type=None):
    conn = boto.ec2.connection.EC2Connection(AWSKEY, AWSPAS)

    reservations = conn.get_all_instances() #filters={'type': 'web'}
    hostnames = []
    for reservation in reservations:
        for instance in reservation.instances:
            if type is None or ('type' in instance.tags and instance.tags['type'] == type):
                hostnames.append(instance.public_dns_name)
    return hostnames

def _s3_signature(resource, expires=None):
    Expires = int(time.time())+100 if expires is None else expires
    HTTPVerb = "GET"
    ContentMD5 = ""
    ContentType = ""
    CanonicalizedAmzHeaders = ""
    CanonicalizedResource = resource
    
    string_to_sign = HTTPVerb + "\n" +  ContentMD5 + "\n" +  ContentType + "\n" + str(Expires) + "\n" + CanonicalizedAmzHeaders + CanonicalizedResource
    sig = base64.b64encode(hmac.new(AWSPAS, string_to_sign, sha).digest())
    return resource + '?' + urllib.urlencode({'AWSAccessKeyId': AWSKEY, 'Expires': Expires, 'Signature':sig})
    

#env.hosts = _get_ec2_hostnames(type='web')
env.key_filename = '/home/trey/Work/aws/basewebkey.pem'
env.user = 'ubuntu'
env.disable_known_hosts = True
env.roledefs = {
    'ftp': functools.partial(_get_ec2_hostnames, type='ftp'),
    'coord': functools.partial(_get_ec2_hostnames, type='coord')
}

def hosts(type='ftp'):
    print '\n'.join(_get_ec2_hostnames(type=type))

@roles('ftp')
def supervisectl(cmd):
    run('supervisorctl ' + cmd)

@roles('coord')
def rewatch():
    sudo('sudo supervisorctl restart watcher')

@roles('ftp')
def relisten():
    sudo('sudo supervisorctl restart listener')

@runs_once
def dist():
    local('python setup.py bdist_egg')

@roles('ftp', 'coord')
def update():
    dist()
    put('./dist/FileCoordinator-0.1-py2.6.egg', 'FileCoordinator-0.1-py2.6.egg')
    sudo('easy_install ~/FileCoordinator-0.1-py2.6.egg')

@roles('ftp')
def config():
    #put('./config/nginx_main.conf', '/etc/nginx/nginx.conf', use_sudo=True)
    put('./config/nginx_defaults.conf', '/etc/nginx/conf.d/defaults.conf', use_sudo=True)
    #put('./config/nginx-fastcgi-params', '/etc/nginx/nginx-fastcgi-params', use_sudo=True)
    #put('./config/supervisor_main.conf', '/etc/supervisor/supervisord.conf', use_sudo=True)
    #put('./config/appwatcher.conf', '/etc/supervisor/conf.d/appwatcher.conf', use_sudo=True)
    #put('./config/listener.conf', '/etc/supervisor/conf.d/listener.conf', use_sudo=True)

@roles('ftp')
def reload(t='nginx'):
    if t == 'nginx':
        sudo('/etc/init.d/nginx reload')






