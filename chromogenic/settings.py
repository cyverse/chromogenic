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
    "SSH_KEY": "",
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
