"""
imaging/clean.py

These functions are used to strip data from a VM before imaging occurs.

"""
import logging, os
from chromogenic.common import check_mounted, prepare_chroot_env,\
remove_chroot_env, run_command, check_distro
from chromogenic.common import (
    remove_files, overwrite_files,
    append_line_in_files, remove_line_in_files,
    replace_line_in_files, remove_multiline_in_files,
    execute_chroot_commands, atmo_required_files, fsck_image, mount_image)

logger = logging.getLogger(__name__)

def remove_user_data(mounted_path, author=None, dry_run=False):
    """
    Remove user data from an image that has already been mounted
    NOTE: This will also include removing *CLOUD* user data.
    """
    if not check_mounted(mounted_path):
        raise Exception("Expected a mounted path at %s" % mounted_path)
    distro = check_distro(mounted_path)
    if 'ubuntu' in distro:
        cloud_user = 'ubuntu'
        remove_user_cmd = '/usr/sbin/userdel'
    elif 'centos' in distro:
        cloud_user = 'centos'
        remove_user_cmd = '/usr/sbin/userdel'
    else:
        cloud_user = ''
        remove_user_cmd = ''
        raise Exception("Encountered unknown distro %s -- Cannot guarantee removal of the cloud-user" % distro)

    remove_files = ['home/*', ]
    overwrite_files = []
    remove_line_files = []
    replace_line_files = [
        #('replace_pattern','replace_with','in_file'),
        ("users:x:100:.*", "users:x:100:", "etc/group"),
        #TODO: Check this should not be 'AllowGroups users core-services root'
        ("AllowGroups users root.*", "", "etc/ssh/sshd_config"),
    ]
    execute_lines = []
    if remove_user_cmd and cloud_user:
        execute_lines.append([remove_user_cmd, '-r', cloud_user])
    if remove_user_cmd and author:
        execute_lines.append([remove_user_cmd, '-r', author])

    multiline_delete_files = [
        #('delete_from', 'delete_to', 'replace_where')
    ]
    _perform_cleaning(mounted_path, rm_files=remove_files,
                      remove_line_files=remove_line_files,
                      overwrite_list=overwrite_files,
                      replace_line_files=replace_line_files, 
                      multiline_delete_files=multiline_delete_files,
                      execute_lines=execute_lines,
                      dry_run=dry_run)


def remove_atmo_data(mounted_path, dry_run=False):
    """
    Remove atmosphere data from an image that has already been mounted
    """
    if not check_mounted(mounted_path):
        raise Exception("Expected a mounted path at %s" % mounted_path)
    remove_files = [#Atmo
                    'etc/rc.local.atmo',
                    'usr/sbin/atmo_boot.py',
                    'var/log/atmo/post-scripts/*',
                    'var/log/atmo/*.log',
                    #Puppet
                    'var/lib/puppet/run/*.pid',
                    'etc/puppet/ssl', 
                    #SSH
                    'root/.ssh',
                   ]
    overwrite_files = []
    remove_line_files = []
    replace_line_files = [
        #('replace_pattern','replace_with','in_file'),
        (".*vncserver$", "", "etc/rc.local"),
        (".*shellinbaox.*", "", "etc/rc.local")
    ]
    multiline_delete_files = [
        #TEMPLATE:
        #('delete_from', 'delete_to', 'replace_where')

        #SUDOERS:
        ("## Atmosphere System", "## End Atmosphere System", "etc/sudoers"),
        ("# Begin Nagios", "# End Nagios", "etc/sudoers"),
        ("# Begin Sensu", "# End Sensu", "etc/sudoers"),
        ("## Atmosphere System", "", "etc/sudoers"), #Delete to end-of-file..
        ("#includedir \/etc\/sudoers.d", "", "etc/sudoers"), #Delete to end-of-file..
        #SSHD_CONFIG:
        ("## Atmosphere System", "## End Atmosphere System",
         "etc/ssh/sshd_config"),
        ("## Atmosphere System", "", "etc/ssh/sshd_config"), #Delete to end-of-file..
        #.BASHRC:
        ("## Atmosphere System", "## End Atmosphere System",
         "etc/skel/.bashrc"),
    ]
    append_line_files = [
        #('append_line','in_file'),
        ("#includedir /etc/sudoers.d", "etc/sudoers"),
    ]
    _perform_cleaning(mounted_path, rm_files=remove_files,
                      remove_line_files=remove_line_files,
                      overwrite_list=overwrite_files,
                      replace_line_files=replace_line_files, 
                      multiline_delete_files=multiline_delete_files,
                      append_line_files=append_line_files,
                      dry_run=dry_run)
    

def remove_vm_specific_data(mounted_path, dry_run=False):
    """
    Remove "VM specific data" from an image that has already been mounted
    this data should include:
    * Logs
    * Pids
    * dev, proc, ...
    """
    if not check_mounted(mounted_path):
        raise Exception("Expected a mounted path at %s" % mounted_path)
    remove_files = [
      'mnt/*', 'mnt/.*',
      'tmp/*', 'tmp/.*',
      'proc/*', 'proc/.*',
      'root/*', 'root/.*',
      # 'dev/*', 'dev/.*'
    ]
    remove_line_files = [
        #("pattern_match", "file_to_test")
        # Save /dev/sda1, /dev/vda, /dev/xvda
        # Delete all other partitions in etc/fstab
        ("sda[2-9]", "etc/fstab"),
        ("sda1[0-9]", "etc/fstab"),
        ("vd[b-z]",  "etc/fstab"),
    ]
    overwrite_files = [
        'etc/udev/rules.d/70-persistent-net.rules',
        'lib/udev/rules.d/75-persistent-net-generator.rules',
        'root/.bash_history', 'var/log/*',
    ]
    replace_line_files = [
        #('replace_pattern','replace_with','in_file'),
        ("HWADDR=*", "", "etc/sysconfig/network-scripts/ifcfg-eth0"),
        ("MACADDR=*", "", "etc/sysconfig/network-scripts/ifcfg-eth0"),
        ("SELINUX=.*", "SELINUX=disabled", "etc/syslinux/selinux"),
        ("SELINUX=.*", "SELINUX=disabled", "etc/selinux/config"),
        ("users:", "#users:", "etc/cloud/cloud.cfg"),
        ("[ ]* - default", "#  - default", "etc/cloud/cloud.cfg"),
        ("disable_root: true", "disable_root: false", "etc/cloud/cloud.cfg"),
        ("disable_root: 1", "disable_root: 0", "etc/cloud/cloud.cfg"),
        ("ssh_deletekeys:.*1", "ssh_deletekeys: 0", "etc/cloud/cloud.cfg"),
        ("ssh_deletekeys:.*true", "ssh_deletekeys: false", "etc/cloud/cloud.cfg"),
    ]
    multiline_delete_files = [
        #('delete_from', 'delete_to', 'replace_where')
    ]
    apt_uninstall(mounted_path, ['avahi-daemon', ])
    package_uninstall(mounted_path, ['fail2ban', ])
    package_install(mounted_path, ['cloud-init', 'cloud-utils'])
    _perform_cleaning(mounted_path, rm_files=remove_files,
                      remove_line_files=remove_line_files,
                      overwrite_list=overwrite_files,
                      replace_line_files=replace_line_files, 
                      multiline_delete_files=multiline_delete_files,
                      dry_run=dry_run)


def _perform_cleaning(mounted_path, rm_files=None,
                      remove_line_files=None, overwrite_list=None,
                      replace_line_files=None, multiline_delete_files=None,
                      append_line_files=None, execute_lines=None, dry_run=False):
    """
    Runs the commands to perform all cleaning operations.
    For more information see the specific function
    """
    remove_files(rm_files, mounted_path, dry_run)
    overwrite_files(overwrite_list, mounted_path, dry_run)
    remove_line_in_files(remove_line_files, mounted_path, dry_run)
    replace_line_in_files(replace_line_files, mounted_path, dry_run)
    remove_multiline_in_files(multiline_delete_files, mounted_path, dry_run)
    append_line_in_files(append_line_files, mounted_path, dry_run)
    execute_chroot_commands(execute_lines, mounted_path, dry_run)

# Commands requiring a 'chroot'


def package_uninstall(mounted_path, package_list):
    distro = check_distro(mounted_path)
    if 'centos' in distro.lower():
        return yum_uninstall(mounted_path, package_list)
    elif 'ubuntu' in distro.lower():
        return apt_uninstall(mounted_path, package_list)


def package_install(mounted_path, package_list):
    distro = check_distro(mounted_path)
    if 'centos' in distro.lower():
        return yum_install(mounted_path, package_list)
    elif 'ubuntu' in distro.lower():
        return apt_install(mounted_path, package_list)


def yum_install(mounted_path, install_list):
    distro = check_distro(mounted_path)
    try:
        prepare_chroot_env(mounted_path)
        for install_item in install_list:
            run_command(["/usr/sbin/chroot", mounted_path,
                         'yum', '-qy', 'install', install_item])
    finally:
        remove_chroot_env(mounted_path)

def apt_install(mounted_path, install_list):
    distro = check_distro(mounted_path)
    try:
        prepare_chroot_env(mounted_path)
        for install_item in install_list:
            run_command(["/usr/sbin/chroot", mounted_path,
                         'apt-get', '-qy', 'install', install_item])
    finally:
        remove_chroot_env(mounted_path)



def yum_uninstall(mounted_path, uninstall_list):
    distro = check_distro(mounted_path)
    if 'centos' not in distro.lower():
        return
    try:
        prepare_chroot_env(mounted_path)
        for uninstall_item in uninstall_list:
            run_command(["/usr/sbin/chroot", mounted_path,
                         'yum', '-qy', 'remove', uninstall_item])
    finally:
        remove_chroot_env(mounted_path)

def apt_uninstall(mounted_path, uninstall_list):
    distro = check_distro(mounted_path)
    if 'ubuntu' not in distro.lower():
        return
    try:
        prepare_chroot_env(mounted_path)
        for uninstall_item in uninstall_list:
            run_command(["/usr/sbin/chroot", mounted_path,
                         'apt-get', '-qy', 'purge', uninstall_item])
    finally:
        remove_chroot_env(mounted_path)

def remove_ldap(mounted_path):
    try:
        prepare_chroot_env(mounted_path)
        run_command(["/usr/sbin/chroot", mounted_path, 'yum',
                     'remove', '-qy', 'openldap'])
    finally:
        remove_chroot_env(mounted_path)

def reset_root_password(mounted_path, new_password='atmosphere'):
    try:
        prepare_chroot_env(mounted_path)
        run_command(["/usr/sbin/chroot", mounted_path, "/bin/bash", "-c",
                     "echo %s | passwd root --stdin" % new_password])
    finally:
        remove_chroot_env(mounted_path)

def file_hook_cleaning(mounted_path, **kwargs):
    """
    Look for a 'file_hook' on the actual filesystem (Mounted at
    mounted_path)

    If it exists, prepare a chroot and execute the file
    """
    #File hooks inside the local image
    clean_filename = kwargs.get('file_hook',"/etc/chromogenic/clean")
    #Ignore the lead / when doing path.join
    not_root_filename = clean_filename[1:]
    mounted_clean_path = os.path.join(mounted_path,not_root_filename)
    if not os.path.exists(mounted_clean_path):
        return False
    try:
        prepare_chroot_env(mounted_path)
        #Run this command in a prepared chroot
        run_command(
            ["/usr/sbin/chroot", mounted_path,
             "/bin/bash", "-c", clean_filename])
    except Exception, e:
        logger.exception(e)
        return False
    finally:
        remove_chroot_env(mounted_path)
    return True


def mount_and_clean(image_path, mount_point, created_by=None, status_hook=None, method_hook=None, **kwargs):
    """
    Clean the local image at <image_path>
    Mount it to <mount_point>
    """
    #Prepare the paths
    if not os.path.exists(image_path):
        logger.error("Could not find local image!")
        raise Exception("Image file not found")

    if not os.path.exists(mount_point):
        os.makedirs(mount_point)
    #FSCK the image, FIRST!
    fsck_image(image_path)
    #Mount the directory
    #NOTE: the 'nbd_device' is not being properly passed through here. As a result, the FINAL umount does not use `qemu-nbd -d`
    result, nbd_device = mount_image(image_path, mount_point)
    if not result:
        raise Exception("Encountered errors mounting the image: %s"
                % image_path)
    if status_hook and hasattr(status_hook, 'on_update_status'):
        status_hook.on_update_status("mounted + cleaning image")
    try:
        #Required cleaning
        remove_user_data(mount_point, author=created_by)
        remove_atmo_data(mount_point)
        remove_vm_specific_data(mount_point)

        #Filesystem cleaning (From within the image)
        file_hook_cleaning(mount_point, **kwargs)

        #Driver specific cleaning
        if method_hook:
            method_hook(image_path, mount_point, **kwargs)

        #Required for atmosphere
        atmo_required_files(mount_point)
        #TODO: call `df -h <mount_point>` and record the `Use%`
        #TODO: IF `Use%` > 90%, set 'new_image=True'
        if status_hook and hasattr(status_hook, 'on_update_status'):
            status_hook.on_update_status("cleaning completed")
    except Exception as exc:
        if status_hook and hasattr(status_hook, 'on_update_status'):
            status_hook.on_update_status("cleaning failed - %s" % exc)
    finally:
        #Don't forget to unmount!
        run_command(['umount', '-lf', mount_point], check_return=True)
        if nbd_device:
            run_command(['qemu-nbd', '-d', nbd_device])
    return True
