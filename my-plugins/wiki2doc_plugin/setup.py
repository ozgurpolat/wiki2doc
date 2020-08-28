from setuptools import find_packages, setup

# name can be any name.  This name will be used to create the .egg file.
# name that is used in packages is the one that is used in the trac.ini file.
# use package name as entry_points
setup(
    name='Tracwiki2doc', version='1.1',
    packages=find_packages(exclude=['*.tests*']),
    entry_points = """
        [trac.plugins]
        wiki2doc = wiki2doc
    """,
    package_data={'wiki2doc': ['templates/*.html',
                               'htdocs/css/*.css',
                               'htdocs/images/*']},
)