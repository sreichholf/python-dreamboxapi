#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""The setup script."""

from setuptools import setup, find_packages

with open('README.md') as readme_file:
    readme = readme_file.read()

with open('CHANGELOG.md') as history_file:
    history = history_file.read()

with open('requirements.txt') as f:
    requirements = f.read().splitlines()

setup_requirements = [ ]

test_requirements = [ ]

setup(
    author="Stephan Reichholf",
    author_email='reichi@opendreambox.org',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    description="Provides a python interface to interact with a dreambox running the official webinterface",
    install_requires=requirements,
    license="MIT license",
    long_description=readme + '\n\n' + history,
    include_package_data=True,
    keywords='dreambox,enigma2',
    name='dreamboxapi',
    packages=find_packages(include=['dreamboxapi']),
    setup_requires=setup_requirements,
    url='https://github.com/sreichholf/python-dreamboxapi',
    version='1.0.4',
    zip_safe=False,
)
