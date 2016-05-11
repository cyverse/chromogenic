import os
import logging
from chromogenic.common import mount_image, remove_files, fsck_image
from chromogenic.common import run_command, atmo_required_files
from chromogenic.common import copy_disk, create_empty_image
from chromogenic.clean import remove_user_data, remove_atmo_data,\
                                  remove_vm_specific_data
from chromogenic.common import prepare_chroot_env, remove_chroot_env

logger = logging.getLogger(__name__)

class BaseDriver():
    def parse_download_args(self, instance_id, **kwargs):
        raise NotImplementedError()
    def parse_upload_args(self, instance_id, **kwargs):
        raise NotImplementedError()
    def download_instance(self, instance_id, download_location, *args, **kwargs):
        raise NotImplementedError()
    def upload_local_image(self, image_location, image_name, *args, **kwargs):
        raise NotImplementedError()

    def create_image(self, instance_id, image_name, *args, **kwargs):
        """
        A 'Basic' create_image pattern. Download, Clean, Upload
        Return the new_image_id
        """
        download_args = self.parse_download_args(**kwargs)
        local_image_path = self.download_instance(instance_id, **download_args)
        self.mount_and_clean(local_image_path, *args, **kwargs)
        upload_args = self.parse_upload_args(instance_id, **kwargs)
        new_image_id = self.upload_local_image(local_image_path, image_name, **upload_args)
        return new_image_id

    def clean_hook(self, image_path, mount_point, exclude=[], *args, **kwargs):
        """
        The image resides in <image_path> and is mounted to <mount_point>.
        Remove all filepaths listed in <exclude>

        Run any driver-specific cleaning here
        """
        #Begin removing user-specified files (Matches wildcards)
        if exclude and exclude[0]:
            logger.info("User-initiated files to be removed: %s" % exclude)
            remove_files(exclude, mount_point)
        return

    def mount_and_clean(self, image_path, mount_point, *args, **kwargs):
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
        try:
            #Required cleaning
            remove_user_data(mount_point, author=kwargs.get('created_by'))
            remove_atmo_data(mount_point)
            remove_vm_specific_data(mount_point)

            #Filesystem cleaning (From within the image)
            self.file_hook_cleaning(mount_point, **kwargs)

            #Driver specific cleaning
            self.clean_hook(image_path, mount_point, *args, **kwargs)

            #Required for atmosphere
            atmo_required_files(mount_point)
            #TODO: call `df -h <mount_point>` and record the `Use%`
            #TODO: IF `Use%` > 90%, set 'new_image=True'
        finally:
            #Don't forget to unmount!
            run_command(['umount', mount_point])
            if nbd_device:
                run_command(['qemu-nbd', '-d', nbd_device])
            #TODO: If `new_image=True`
            #          replace disk image location with the 'new, larger disk'
        return

    def file_hook_cleaning(self, mounted_path, **kwargs):
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

    def _get_file_size_gb(self, filename):
        #TODO: Move to export.py
        import math
        byte_size = os.path.getsize(filename)
        one_gb = 1024**3
        gb_size = math.ceil( float(byte_size)/one_gb )
        return int(gb_size)

    def _copy_image(self, local_img_path, pad_size=1, ext='raw'):
        #Image is now ready to be placed on a bootable drive, then install grub-legacy
        image_size = self._get_file_size_gb(local_img_path)
        local_raw_path = local_img_path +  "." + ext
        create_empty_image(local_raw_path, ext,
                           image_size+pad_size,  # Add some empty space..
                           bootable=True)
        download_dir = os.path.dirname(local_img_path)
        mount_point = os.path.join(download_dir,"mount_point/")
        #copy the data
        copy_disk(old_image=local_img_path,
                  new_image=local_raw_path,
                  download_dir=download_dir)
        #TODO: Grow filesystem via OS??
        return local_raw_path


