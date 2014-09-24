import setuptools
from chromogenic.version import get_version, read_requirements

readme = open('README.md').read()
dependencies, requirements = read_requirements('requirements.txt')

long_description = readme

setuptools.setup(
    name='chromogenic',
    version=get_version('short'),
    author='iPlant Collaborative',
    author_email='atmodevs@gmail.com',
    description="A unified imaging interface supporting multiple cloud providers.",
    long_description=long_description,
    license="Apache License, Version 2.0",
    url="https://github.com/iPlantCollaborativeOpenSource/chromogenic",
    packages=setuptools.find_packages(),
    dependency_links=dependencies,
    install_requires=requirements,
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
