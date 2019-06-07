"""
imaging/clean.py

These functions are used to strip data from a VM before imaging occurs.

"""
import logging, os
from chromogenic.common import prepare_chroot_env,\
remove_chroot_env, run_command, check_distro
from chromogenic.common import (
    remove_files, overwrite_files,
    append_line_in_files, remove_line_in_files,
    replace_line_in_files, remove_multiline_in_files,
    execute_chroot_commands, fsck_image, mount_image)
import chromogenic.virt_sysprep as virt_sysprep_files

logger = logging.getLogger(__name__)


# Commands requiring a 'chroot'

# still used in drivers/virtualbox.py
def remove_ldap(mounted_path):
    try:
        prepare_chroot_env(mounted_path)
        run_command(["/usr/sbin/chroot", mounted_path, 'yum',
                     'remove', '-qy', 'openldap'])
    finally:
        remove_chroot_env(mounted_path)

# still used in drivers/virtualbox.py
def reset_root_password(mounted_path, new_password='atmosphere'):
    try:
        prepare_chroot_env(mounted_path)
        run_command(["/usr/sbin/chroot", mounted_path, "/bin/bash", "-c",
                     "echo %s | passwd root --stdin" % new_password])
    finally:
        remove_chroot_env(mounted_path)


def mount_and_clean(image_path, created_by=None, status_hook=None, method_hook=None, **kwargs):
    """
    Clean the local image at <image_path>
    """
    #Prepare the paths
    if not os.path.exists(image_path):
        logger.error("Could not find local image!")
        raise Exception("Image file not found")

    #FSCK the image, FIRST!
    fsck_image(image_path)

    # Figure out distro using virt-inspect
    import subprocess
    output = subprocess.Popen(['virt-inspector', '-a', image_path], stdout=subprocess.PIPE).stdout.read()
    distro = output[output.find('<distro>') + 8 : output.find('</distro>')]
    fstrim = 'run-command fstrim --all' if '<name>util-linux</name>' in output else ''

    # Check that cloud-init is installed because virt-sysprep is currently unable to install it
    if '<name>cloud-init</name>' not in output:
        raise Exception("cloud-init is not installed on this image so it will fail to deploy on Atmosphere")

    # Get filename and content based off distro
    vs_filename = "{}/virt-sysprep-{}.txt".format(os.path.dirname(image_path), distro)
    vs_content = virt_sysprep_files.commands % (getattr(virt_sysprep_files, distro), fstrim)

    # Create file if it does not exist
    if not os.path.exists(vs_filename):
        with open(vs_filename, 'w+') as vs_file:
            vs_file.write(vs_content)

    # Use virt-sysprep to clean image
    logger.info("Running virt-sysprep for distro {}".format(distro))
    proc = subprocess.Popen([
        'virt-sysprep',
        '-a', image_path,
        '--operations', 'defaults,kerberos-data,user-account',
        '--hostname', distro,
        '--commands-from-file', vs_filename
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out,err = proc.communicate()
    rc = proc.returncode
    logger.info("virt-sysprep out: {}".format(out))
    if rc != 0:
        logger.error("virt-sysprep exited with code {} and message: {}".format(rc, err))
        raise Exception("virt-sysprep failed on image file {} with error: {}".format(image_path, err))
