import os, os.path
from hashlib import md5

BUFFER_SIZE = 8192

def command(name, *a):
    return [name, a]

def get_file_contents(filename):
    with open(filename, 'rb') as fp:
        return fp.read()

def calculate_md5(filename):
    m = md5()
    with open(filename, 'rb') as fp:
        s = fp.read(BUFFER_SIZE)
        while s:
            m.update(s)
            s = fp.read(BUFFER_SIZE)
    hex_md5 = m.hexdigest()
    return hex_md5

def strip_local_path(filename, path):
    filename = filename[len(path):]
    if filename.startswith('/'):
        filename = filename[1:]
    return filename

def generate_file_tree(top):
    #Generate file tree relative to top dir.
    for path, dirlist, filelist in os.walk(top):
        for f in filelist:
            yield os.path.join(path, f)

def generate_file_hash(files):
    for f in files:
        yield f, calculate_md5(f)

def generate_file_paths(tuples, top_dir):
    for path, md5 in tuples:
        yield strip_local_path(path, top_dir), md5