"""
This module sets up setup script using setuptools

name can be any name.  This name will be used to create .egg file.
name that is used in packages is the one that is used in the trac.ini file.
use package name as entry_points

Classes: N/A
Functions: setup(name, packages, entry_points, package_data)
"""

from setuptools import find_packages, setup

setup(
    name='Tracwiki2doc',
    version='1.1',
    packages=find_packages(exclude=['*.tests*']),
    entry_points="""
        [trac.plugins]
        wiki2doc = wiki2doc
    """,
    package_data={'wiki2doc': ['templates/*.html',
                               'htdocs/css/*.css',
                               'htdocs/images/*']},
)
