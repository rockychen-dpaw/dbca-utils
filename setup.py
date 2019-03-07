from setuptools import setup, find_packages

setup(
    name='dbca-utils',
    version='1.0.1',
    packages=find_packages(),
    description='Utilities for Django/Python apps',
    url='https://github.com/dbca-wa/dpaw-utils',
    author='Department of Biodiversity, Conservation and Attractions',
    author_email='asi@dbca.wa.gov.au',
    license='Apache License, Version 2.0',
    zip_safe=False,
    install_requires=[
        'requests',
        'six',
    ]
)
