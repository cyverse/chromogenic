from chromogenic.common import mount_image, remove_files
from chromogenic.common import run_command
from chromogenic.clean import remove_user_data, remove_atmo_data,\
                                  remove_vm_specific_data

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

        #Mount the directory
        out, err = mount_image(image_path, mount_point)
        if err:
            raise Exception("Encountered errors mounting the image: %s" % err)
        #Required cleaning
        remove_user_data(mount_point)
        remove_atmo_data(mount_point)
        remove_vm_specific_data(mount_point)
        #Driver specific cleaning
        self.clean_hook(image_path, mount_point, *args, **kwargs)
        #Don't forget to unmount!
        run_command(['umount', mount_point])
        return


