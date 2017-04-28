import os
import logging
from chromogenic.common import mount_image, remove_files, fsck_image
from chromogenic.common import run_command, atmo_required_files
from chromogenic.common import copy_disk, create_empty_image
from chromogenic.clean import mount_and_clean
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
        mount_and_clean(
                local_image_path,
                status_hook=getattr(self, 'hook', None),
                method_hook=getattr(self, 'clean_hook',None),
                *args, **kwargs)
        upload_args = self.parse_upload_args(instance_id, **kwargs)
        new_image_id = self.upload_local_image(local_image_path, image_name, **upload_args)
        return new_image_id

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


