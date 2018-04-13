import setuptools
from chromogenic.version import get_version

readme = open('README.md').read()

long_description = readme

setuptools.setup(
    name='chromogenic',
    version=get_version('short'),
    author='CyVerse',
    author_email='atmo-dev@cyverse.org',
    description="A unified imaging interface supporting multiple cloud providers.",
    long_description=long_description,
    license="Apache License, Version 2.0",
    url="https://github.com/cyverse/chromogenic",
    packages=setuptools.find_packages(),
    dependency_links=[],
    install_requires=[
        "threepio",
        "rtwo",
        "boto",
        "python-glanceclient",
        "python-keystoneclient",
        "python-novaclient"
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Topic :: Software Development :: Libraries",
        "Topic :: System",
        "Topic :: System :: Distributed Computing",
        "Topic :: System :: Systems Administration"
    ])
