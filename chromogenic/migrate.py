import os

from threepio import logger

from chromogenic.common import wildcard_remove
from chromogenic.drivers.migration import KVM2Xen, Xen2KVM

def migrate_instance(origCls, orig_creds, migrateCls, migrate_creds, **imaging_args):
    orig = origCls(**orig_creds)
    migrate = migrateCls(**migrate_creds)
    manager = orig

    #1. Download from orig
    download_kwargs = manager.download_instance_args(**imaging_args)

    download_location = manager.download_instance(**download_kwargs)
    imaging_args['download_location'] = download_location
    start_migration(origCls, orig_creds, migrateCls, migrate_creds,
                    **imaging_args)

def migrate_image(origCls, orig_creds, migrateCls, migrate_creds, **imaging_args):
    orig = origCls(**orig_creds)
    migrate = migrateCls(**migrate_creds)
    manager = orig

    #1. Download from orig
    download_kwargs = manager.download_image_args(**imaging_args)
    download_location = manager.download_image(**download_kwargs)
    imaging_args['download_location'] = download_location
    start_migration(origCls, orig_creds, migrateCls, migrate_creds,
                    **imaging_args)

def start_migration(origCls, orig_creds, migrateCls, migrate_creds,
                    download_location, **imaging_args):
    download_dir = os.path.dirname(download_location)
    mount_point = os.path.join(download_dir, 'mount/')
    if not os.path.exists(mount_point):
        os.makedirs(mount_point)
    #2. clean from orig
    if imaging_args.get('clean_image',True):
        manager.mount_and_clean(
                download_location,
                mount_point,
                **imaging_args)

        #2. clean from new
        migrate.mount_and_clean(
                download_location,
                mount_point,
                **imaging_args)

    #3. Convert from KVM-->Xen or Xen-->KVM (If necessary)
    if imaging_args.get('kvm_to_xen', False):
        (image_path, kernel_path, ramdisk_path) =\
            KVM2Xen.convert(download_location, download_dir)
    elif imaging_args.get('xen_to_kvm', False):
        (image_path, kernel_path, ramdisk_path) =\
            Xen2KVM.convert(download_location, download_dir)
    imaging_args['image_path'] = image_path
    imaging_args['kernel_path'] = kernel_path
    imaging_args['ramdisk_path'] = ramdisk_path
    #4. Upload on new
    upload_kwargs = migrate.parse_upload_args(**imaging_args)
    new_image_id = migrate.upload_image(**upload_kwargs)

    #5. Cleanup, return
    if imaging_args.get('keep_image',False):
        wildcard_remove(download_dir)
    return new_image_id
