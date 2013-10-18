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
import glob
import shutil

from threepio import logger

from chromogenic.drivers.openstack import ImageManager as OSImageManager
from chromogenic.drivers.eucalyptus import ImageManager as EucaImageManager
from chromogenic.common import run_command
from chromogenic.common import mount_image
from chromogenic.convert import xen_to_kvm_ubuntu
from chromogenic.convert import xen_to_kvm_centos


        
def xen_debian_migration(self, image_path, download_dir, euca_image_id):
    """
    Convert the disk image at image_path from XEN to KVM
    """
    #!!!IMPORTANT: Change this version if there is an update to the KVM kernel

    kernel_dir = os.path.join(download_dir,"kernel")
    ramdisk_dir = os.path.join(download_dir,"ramdisk")
    mount_point = os.path.join(download_dir,"mount_point")

    for dir_path in [kernel_dir, ramdisk_dir, mount_point]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

    #Mount the image
    mount_image(image_path, mount_point)

    xen_to_kvm_ubuntu(mount_point)

    #Un-mount the image
    run_command(["umount", mount_point])

    image = self.euca_img_manager.get_image(euca_image_id)
    kernel = self.euca_img_manager.get_image(image.kernel_id)
    ramdisk = self.euca_img_manager.get_image(image.ramdisk_id)

    kernel_fname  = self.euca_img_manager._download_euca_image(
        kernel.location, kernel_dir, 
        kernel_dir, self.euca_img_manager.pk_path)[0]
    ramdisk_fname = self.euca_img_manager._download_euca_image(
        ramdisk.location, ramdisk_dir,
        ramdisk_dir, self.euca_img_manager.pk_path)[0]

    kernel_path = os.path.join(kernel_dir,kernel_fname)
    ramdisk_path = os.path.join(ramdisk_dir,ramdisk_fname)

    return (image_path, kernel_path, ramdisk_path)

def xen_rhel_migration(self, image_path, download_dir):
    """
    Migrate RHEL systems from XEN to KVM
    Returns: ("/path/to/img", "/path/to/kernel", "/path/to/ramdisk")
    """
    (kernel_dir, ramdisk_dir, mount_point) = self._export_dirs(download_dir)

    #Labeling the image as 'root' allows for less reliance on UUID
    run_command(['e2label', image_path, 'root'])

    out, err = mount_image(image_path, mount_point)
    if err:
        raise Exception("Encountered errors mounting the image: %s" % err)

    xen_to_kvm_centos(mount_point)

    #Determine the latest (KVM) ramdisk to use
    latest_rmdisk, rmdisk_version = get_latest_ramdisk(mount_point)

    #Copy new kernel & ramdisk to the folder
    local_ramdisk_path = self._copy_ramdisk(mount_point, rmdisk_version, ramdisk_dir)
    local_kernel_path = self._copy_kernel(mount_point, rmdisk_version, kernel_dir)

    run_command(["umount", mount_point])

    #Your new image is ready for upload to OpenStack 
    return (image_path, local_kernel_path, local_ramdisk_path)
