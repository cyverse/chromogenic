"""
Current logger version.
"""
import re

from subprocess import Popen, PIPE
from os.path import abspath, dirname

VERSION = (0, 0, 1, 'dev', 0)

egg_regex = re.compile("(?P<egg>.*)-(?P<version>[0-9.].*)$")

def dependencies(requirements_file):
    return read_requirements(requirements_file, False)

def git_dependencies(requirements_file):
    return read_requirements(requirements_file, True)

def convert_version(egg):
    r = egg_regex.search(egg)
    if not r:
        return egg
    group = r.groupdict()
    return "%s==%s" % (group['egg'], group['version'])

def read_requirements(requirements_file, git=False):
    deps = []
    with open(requirements_file, 'r') as f:
        for line in f.read().split('\n'):
            #Skip empty spaces
            if not line:
                continue
            #Add git if looking for git
            if 'git+git' in line:
                if git:
                    #Add to dependency_links
                    deps.append(line)
                else:
                    #Add just the egg name to 
                    # The dependency is the egg name
                    dep_split = line.split('#egg=')
                    if len(dep_split) > 1:
                        git_link, egg = dep_split
                        # Remove branch information from the egg
                        requirement = convert_version(egg)
                        deps.append(requirement)
            #Add requirements if not looking for git
            elif not git:
                deps.append(line)
    return deps

def git_sha():
    loc = abspath(dirname(__file__))
    try:
        p = Popen(
            "cd \"%s\" && git log -1 --format=format:%%h" % loc,
            shell=True,
            stdout=PIPE,
            stderr=PIPE
        )
        return p.communicate()[0]
    except OSError:
        return None

def get_version(form='short'):
    """
    Returns the version string.

    Takes single argument ``form``, which should be one of the following
    strings:
    
    * ``short`` Returns major + minor branch version string with the format of
    B.b.t.
    * ``normal`` Returns human readable version string with the format of 
    B.b.t _type type_num.
    * ``verbose`` Returns a verbose version string with the format of
    B.b.t _type type_num@git_sha
    * ``all`` Returns a dict of all versions.
    """
    versions = {}
    branch = "%s.%s" % (VERSION[0], VERSION[1])
    tertiary = VERSION[2]
    type_ = VERSION[3]
    type_num = VERSION[4]
    
    versions["branch"] = branch
    v = versions["branch"]
    if tertiary:
        versions["tertiary"] = "." + str(tertiary)
        v += versions["tertiary"]
    versions['short'] = v
    if form is "short":
        return v
    v += " " + type_ + " " + str(type_num)
    versions["normal"] = v
    if form is "normal":
        return v
    v += " @" + git_sha()
    versions["verbose"] = v
    if form is "verbose":
        return v
    if form is "all":
        return versions

