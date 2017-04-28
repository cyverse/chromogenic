import os

import logging

from chromogenic.common import wildcard_remove
from chromogenic.clean import mount_and_clean
from chromogenic.drivers.migration import KVM2Xen, Xen2KVM

logger = logging.getLogger(__name__)

def migrate_instance(src_managerCls, src_manager_creds, migrationCls, migration_creds, **imaging_args):
    """
    Use the source manager to download a local image file
    Then start the migration by passing migration class
    """
    src_manager = src_managerCls(**src_manager_creds)
    src_manager.hook = imaging_args.get('machine_request', None)

    #1. Download from src_manager
    download_kwargs = src_manager.download_instance_args(**imaging_args)
    snapshot_id, download_location = src_manager.download_instance(**download_kwargs)
    imaging_args['download_location'] = download_location
    #Clean it
    download_dir = os.path.dirname(download_location)
    mount_point = os.path.join(download_dir, 'mount_point/')
    if not os.path.exists(mount_point):
        os.makedirs(mount_point)
    if imaging_args.get('clean_image',True):
        mount_and_clean(
                download_location,
                mount_point,
                status_hook=getattr(src_manager, 'hook', None),
                method_hook=getattr(src_manager, 'clean_hook', None),
                **imaging_args)
    #2. Start the migration
    return start_migration(migrationCls, migration_creds, **imaging_args)

def migrate_image(src_managerCls, src_manager_creds, migrationCls, migration_creds, **imaging_args):
    """
    Use the source manager to download a local image file
    Then start the migration by passing migration class
    """
    src_manager = src_managerCls(**src_manager_creds)
    src_manager.hook = imaging_args.get('machine_request', None)

    #1. Download & clean from src_manager
    download_kwargs = src_manager.download_image_args(**imaging_args)
    download_location = src_manager.download_image(**download_kwargs)
    #Clean it
    download_dir = os.path.dirname(download_location)
    mount_point = os.path.join(download_dir, 'mount_point/')
    if not os.path.exists(mount_point):
        os.makedirs(mount_point)
    imaging_args['download_location'] = download_location
    if imaging_args.get('clean_image',True):
        mount_and_clean(
                download_location,
                mount_point,
                status_hook=getattr(src_manager, 'hook', None),
                method_hook=getattr(src_manager, 'clean_hook', None),
                **imaging_args)

    #2. Start the migration
    return start_migration(migrationCls, migration_creds, **imaging_args)

def start_migration(migrationCls, migration_creds, download_location, **imaging_args):
    """
    Whether your migration starts by image or by instance, they all end the
    same:
    * Clean-up the local image file
    * Upload the local image file
    """
    dest_manager = migrationCls(**migration_creds)
    dest_manager.hook = imaging_args.get('machine_request', None)
    download_dir = os.path.dirname(download_location)
    mount_point = os.path.join(download_dir, 'mount_point/')
    if not os.path.exists(mount_point):
        os.makedirs(mount_point)
    #2. clean using dest manager
    if imaging_args.get('clean_image',True):
        mount_and_clean(
                download_location,
                mount_point,
                status_hook=getattr(dest_manager, 'hook', None),
                method_hook=getattr(dest_manager, 'clean_hook', None),
                **imaging_args)

    #3. Convert from KVM-->Xen or Xen-->KVM (If necessary)
    if imaging_args.get('kvm_to_xen', False):
        (image_path, kernel_path, ramdisk_path) =\
            KVM2Xen.convert(download_location, download_dir)
        imaging_args['image_path'] = image_path
        imaging_args['kernel_path'] = kernel_path
        imaging_args['ramdisk_path'] = ramdisk_path
    elif imaging_args.get('xen_to_kvm', False):
        (image_path, kernel_path, ramdisk_path) =\
            Xen2KVM.convert(download_location, download_dir)
        imaging_args['image_path'] = image_path
        imaging_args['kernel_path'] = kernel_path
        imaging_args['ramdisk_path'] = ramdisk_path
    else:
        logger.info("Upload requires no conversion between Xen and KVM.")
        imaging_args['image_path'] = download_location
    #4. Upload on new
    imaging_args['download_location'] = download_location
    upload_kwargs = dest_manager.parse_upload_args(**imaging_args)
    new_image_id = dest_manager.upload_image(**upload_kwargs)

    #5. Cleanup, return
    if not imaging_args.get('keep_image',False):
        wildcard_remove(download_dir)
    return new_image_id
