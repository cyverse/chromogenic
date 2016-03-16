# -*- coding: utf-8 -*-
"""
Settings for the authentication app.
"""

from django.conf import settings
from django.test.signals import setting_changed
import sys
import os

APP_DIRECTORY = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, APP_DIRECTORY)
#NOTE: if 'SECRETS_MODULE' is enabled, chromogenic settings should be kept there.
if hasattr(settings, 'SECRETS_MODULE'):
    if hasattr(settings, 'CHROMOGENIC'):
        raise Exception(
            "Move definition of 'CHROMOGENIC' *OUT* of your local.py and "
            "into the file defined in SECRETS_MODULE")
    settings = getattr(settings, 'SECRETS_MODULE')


USER_SETTINGS = getattr(settings, 'CHROMOGENIC', {})


DEFAULTS =  {
    # General
    "SSH_KEY": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDVVkgGS8QwHet+aF401l6MLD206yfE76Pe8UAbWhKdE1155IHyDumS5226cTf+5/1zqyzlGwvHJMhzJEztImJghXAWMw7AOzDUYmIpGGhnvmVE1mJN6Iy3aRDyJOcPOqd1ZGbywzzQioiYjoxKa/HT5QN5F/4Mdsqn3mgFdWgXxmY7X3fZGphk5vOK/8J8tSpy4dLIBI+WRrN4ZR7IOrvzkZght/YjtvgPhJqZzgEzcTP4BMpUNWlOFL95Usk3lzqJTBDzlM71ivaHQ3OqxrjpThMSGoQhedupsx8FrmBvOo1OxjfIj0/hIEtjH9FE2lc5GZBy7B1EuqXApR7Vopa3 atmo@iplantcollaborative.org",
}


class ReadOnlyAttrDict(dict):
    __getattr__ = dict.__getitem__

new_settings = DEFAULTS.copy()
new_settings.update(USER_SETTINGS)
# This 'settings' instance will be used in the code
chromo_settings = ReadOnlyAttrDict(new_settings)


def reload_settings(*args, **kwargs):
    global chromo_settings
    setting_name, values = kwargs['setting'], kwargs['value']
    if setting_name == "CHROMOGENIC":
        defaults = DEFAULTS.copy()
        chromo_settings = ReadOnlyAttrDict(defaults.update(values))


setting_changed.connect(reload_settings)
