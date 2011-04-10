#!/usr/bin/env python
from distutils.core import setup

setup(
    name='FileCoordinator',
    version='0.1',
    description='Network Based File Sync',
    author='Trey Long',
    author_email='trey@ktrl.com',
    packages=['pyzmq', 'pyinotify'])