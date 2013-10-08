import os
import setuptools
from chromogenic.version import get_version, git_dependencies, dependencies

readme = open('README.md').read()

long_description = """
rtwo %s
A unified interface into multiple cloud providers.

To install use pip install git+git://git@github.com:iPlantCollaborativeOpenSource/rtwo.git

----

%s

----

For more information, please see: https://github.com/iPlantCollaborativeOpenSource/rtwo
""" % (get_version('short'), readme)

setuptools.setup(
    name='chromogenic',
    version=get_version('short'),
    author='steve-gregory',
    author_email='contact@steve-gregory.com',
    description="A unified imaging interface supporting multiple cloud providers.",
    long_description=long_description,
    license="Apache License, Version 2.0",
    url="https://github.com/iPlantCollaborativeOpenSource/chromogenic-cloud",
    packages=setuptools.find_packages(),
    dependency_links=git_dependencies('requirements.txt'),
    install_requires=dependencies('requirements.txt'),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Topic :: Software Development :: Libraries",
        "Topic :: System",
        "Topic :: System :: Clustering",
        "Topic :: System :: Distributed Computing",
        "Topic :: System :: Systems Administration"
    ])
