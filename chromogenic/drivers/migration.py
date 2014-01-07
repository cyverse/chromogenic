"""
MigrationManager:
    Use this class to describe processes to move images from one cloud to another

Migrating an Instance/Image (Example: Eucalyptus --> Openstack)
>> manager.migrate_image('/temp/image/path/', 'emi-F1F122E4')
    _OR_
>> manager.migrate_instance('/temp/image/path/', 'i-12345678')

>> os_manager.upload_euca_image('Migrate emi-F1F122E4', 
                                '/temp/image/path/name_of.img', 
                                '/temp/image/path/kernel/vmlinuz-...el5', 
                                '/temp/image/path/ramdisk/initrd-...el5.img')
"""
import os

import logging

from chromogenic.common import create_file, mount_image, run_command,\
                               check_distro, apply_label, build_imaging_dirs

from chromogenic.common import prepare_chroot_env,\
                               remove_chroot_env

from chromogenic.common import retrieve_kernel_ramdisk,\
                               rebuild_ramdisk

from chromogenic.common import append_line_in_files,\
                               prepend_line_in_files,\
                               remove_line_in_files,\
                               replace_line_in_files,\
                               remove_multiline_in_files,\
                               remove_files

logger = logging.getLogger(__name__)

class MigrationPlan():
    """
    Migration Plans are used to convert an image between two virtualization
    softwares

    The programmer should define a set of steps that are required to convert
    any image (taking into account different distributions)

    The user should provide a path to a local image file and call
    MigrationPlan.convert(...)
    """
    @classmethod
    def convert(cls, image_path, upload_dir):
        (kernel_dir, ramdisk_dir, mount_point) = build_imaging_dirs(upload_dir,
                full_image=True)

        apply_label(image_path, label='root')  # TODO: Is this necessary?

        try:
            out, err = mount_image(image_path, mount_point)
            if err:
                raise Exception("Encountered errors mounting image:%s" % err)

            #Our mount_point is in use, the image is mounted at this path
            mounted_path = mount_point
            distro = check_distro(mounted_path)

            #Hooks for debian/rhel specific cleaning commands
            if distro == 'ubuntu':
                 cls.debian_mount(image_path, mount_point)
            elif distro == 'centos':
                 cls.rhel_mount(image_path, mount_point)

            try:
                prepare_chroot_env(mounted_path)
                #Hooks for debian/rhel specific chroot commands
                if distro == 'ubuntu':
                     cls.debian_chroot(image_path, mount_point)
                elif distro == 'centos':
                     cls.rhel_chroot(image_path, mount_point)
            finally:
                remove_chroot_env(mounted_path)

            (kernel_path, ramdisk_path) = cls.get_kernel_ramdisk(mount_point,
                                                    kernel_dir, ramdisk_dir)
    
            #Use the image, kernel, and ramdisk paths
            #to initialize any driver that implements 'upload_full_image'
            return (image_path, kernel_path, ramdisk_path)
        finally:
            run_command(["umount", mount_point])

    @classmethod
    def rhel_chroot(cls, image_path, mounted_path):
        logger.warn("This method is not implemented by default")
        return

    @classmethod
    def debian_chroot(cls, image_path, mounted_path):
        logger.warn("This method is not implemented by default")
        return

    @classmethod
    def rhel_mount(cls, image_path, mounted_path):
        logger.warn("This method is not implemented by default")
        return

    @classmethod
    def debian_mount(cls, image_path, mounted_path):
        logger.warn("This method is not implemented by default")
        return
    @classmethod
    def get_kernel_ramdisk(cls, mount_point, kernel_dir, ramdisk_dir):
        logger.warn("This method is not implemented by default")
        return




class KVM2Xen(MigrationPlan):
    """
    This MigrationPlan is a STUB
    It should define a path to convert KVM images to XEN images
    """
    @classmethod
    def get_kernel_ramdisk(cls, mount_point, kernel_dir, ramdisk_dir):
        #Rebuild ramdisk in case changes were made
        rebuild_ramdisk(mount_point, ignore_suffix='el5')
        #Retrieve the kernel/ramdisk pair and return
        (kernel_path,
         ramdisk_path) = retrieve_kernel_ramdisk(mount_point,
                                                 kernel_dir, ramdisk_dir,
                                                 ignore_suffix='el5')
        return (kernel_path, ramdisk_path)

class Xen2KVM(MigrationPlan):
    """
    This MigrationPlan will convert a XEN image to KVM image
    """

    @classmethod
    def get_kernel_ramdisk(cls, mount_point, kernel_dir, ramdisk_dir):
        #Rebuild ramdisk in case changes were made
        rebuild_ramdisk(mount_point, ignore_suffix='el5xen')
        #Retrieve the kernel/ramdisk pair and return
        (kernel_path, ramdisk_path) = retrieve_kernel_ramdisk(mount_point,
                                                 kernel_dir, ramdisk_dir,
                                                 ignore_suffix='el5xen')
        return (kernel_path, ramdisk_path)
    @classmethod
    def debian_chroot(cls, image_path, mounted_path):
        #Here is an example of how to run a command in chroot:
        #run_command(["/usr/sbin/chroot", mounted_path, "/bin/bash", "-c",
        #             "./single/command.sh arg1 arg2 ..."])
        #Run this command in a prepared chroot
        run_command(["/usr/sbin/chroot", mounted_path, "/bin/bash", "-c",
                     "apt-get install -qy linux-image initramfs-tools grub"])
        pass

    @classmethod
    def rhel_chroot(cls, image_path, mounted_path):
        #Here is an example of how to run a command in chroot:
        #run_command(["/usr/sbin/chroot", mounted_path, "/bin/bash", "-c",
        #             "./single/command.sh arg1 arg2 ..."])
        run_command(["/usr/sbin/chroot", mounted_path, "/bin/bash", "-c",
                     "yum install -qy kernel mkinitrd grub"])
        pass

    @classmethod
    def debian_mount(self, image_path, mounted_path):
        """
        Convert the disk image at <image_path>, mounted at <mounted_path>,
        from XEN to KVM
        """
        #This list will add a single line to an already-existing file
        append_line_file_list = [
                #("line to add", "file_to_append")
                ("exec /sbin/getty -L 38400 ttyS0 vt102", "etc/init/getty.conf"),
                ("exec /sbin/getty -L 38400 ttyS1 vt102", "etc/init/getty.conf"),
        ]
    
        #If etc/init/getty.conf doesn't exist, use this template to create it
        kvm_getty_script = """# getty - ttyS*
# This service maintains a getty on ttyS0/S1
# from the point the system is started until
# it is shut down again.

start on stopped rc RUNLEVEL=[2345]
stop on runlevel [!2345]

respawn
exec /sbin/getty -L 38400 ttyS0 vt102
exec /sbin/getty -L 38400 ttyS1 vt102
"""
    
        #This list removes lines matching the pattern from an existing file
        remove_line_file_list = [
                #("pattern_match", "file_to_test")
                ("atmo_boot",  "etc/rc.local"),
                ("sda2", "etc/fstab"),
                ("sda3",  "etc/fstab")]
    
        # This list contains all files that should be deleted
        remove_file_list = [
                'etc/init/hvc0.conf']
    
        remove_line_in_files(remove_line_file_list, mounted_path)
        remove_files(remove_file_list, mounted_path)
        if not create_file("etc/init/getty.conf", mounted_path, kvm_getty_script):
            #Didn't need to create the file, but we still need to append our
            # new lines
            append_line_in_files(append_line_file_list, mounted_path)
        return

    @classmethod
    def rhel_mount(cls, image_path, mounted_path):
        """
        Migrate RHEL systems from XEN to KVM
        Returns: ("/path/to/img", "/path/to/kvm_kernel", "/path/to/kvm_ramdisk")
        """
        #This list will append a single line to an already-existing file
        append_line_file_list = [
                #("line to add", "file_to_append")
                ("S0:2345:respawn:/sbin/agetty ttyS0 115200", "etc/inittab"),
                ("S1:2345:respawn:/sbin/agetty ttyS1 115200", "etc/inittab"),
        ]

        #TODO: This etc/fstab line may need some more customization

        #This list will prepend a single line to an already-existing file
        prepend_line_list = [
            #("line to prepend", "file_to_prepend")
            ("LABEL=root\t\t/\t\t\text3\tdefaults,errors=remount-ro 0 0",
            "etc/fstab"),
            ]
        #This list removes lines matching the pattern from an existing file
        remove_line_file_list = [#("pattern_match", "file_to_test")
                                 ("alias scsi", "etc/modprobe.conf"),
                                 ("atmo_boot", "etc/rc.local")]

        # This list replaces lines matching a pattern from an existing file
        replace_line_file_list = [#(pattern_match, pattern_replace, file_to_match)
                                  ("^\/dev\/sda", "\#\/dev\/sda", "etc/fstab"),
                                  ("^xvc0", "\#xvc0", "etc/inittab"),
                                  ("xenblk", "ata_piix", "etc/modprobe.conf"),
                                  ("xennet", "8139cp", "etc/modprobe.conf")]
        #This list removes ALL lines between <pattern_1> and <pattern_2> from an
        # existing file
        multiline_delete_files = [
            #("delete_from","delete_to","file_to_match")
            ("depmod -a","\/usr\/bin\/ruby \/usr\/sbin\/atmo_boot", "etc/rc.local"),
            ("depmod -a","\/usr\/bin\/ruby \/usr\/sbin\/atmo_boot", "etc/rc.d/rc.local")
        ]

        append_line_in_files(append_line_file_list, mounted_path)
        prepend_line_in_files(prepend_line_list, mounted_path)
        remove_line_in_files(remove_line_file_list, mounted_path)
        replace_line_in_files(replace_line_file_list, mounted_path)
        remove_multiline_in_files(multiline_delete_files, mounted_path)
