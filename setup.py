#!/usr/bin/env python
from setuptools import setup, find_packages

setup(
    name='FileCoordinator',
    version='0.1',
    description='Network Based File Sync',
    author='Trey Long',
    author_email='trey@ktrl.com',
    packages=find_packages(),
    entry_points = {
        'console_scripts':
            ['watcher = coordinator.watcher:main',
             'listener = coordinator.listener:main',
             'ngdeploy = coordinator.deploy:main',
             'watchexec = coordinator.watchexec:main'],
    },
    install_requires=['pyzmq', 'pyinotify'])