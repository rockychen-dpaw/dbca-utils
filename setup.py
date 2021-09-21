#!/usr/bin/env python

from setuptools import setup

setup(
    name='dbca-utils',
    version='0.1.5',
    packages=['dbca_utils'],
    description='Utilities for Django/Python apps',
    url='https://github.com/dbca-wa/dbca-utils',
    author='Department of Biodiversity, Conservation and Attractions',
    author_email='asi@dbca.wa.gov.au',
    maintainer='Department of Biodiversity, Conservation and Attractions',
    maintainer_email='asi@dbca.wa.gov.au',
    license='Apache License, Version 2.0',
    zip_safe=False,
    keywords=['django', 'middleware', 'utility'],
    install_requires=[
        'Django<2.0',
        'requests',
    ],
    classifiers=[
        'Framework :: Django',
        'Framework :: Django :: 1',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Topic :: Software Development :: Libraries',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
