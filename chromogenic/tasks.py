import os, re

from datetime import datetime

from celery.decorators import task

from threepio import logger

from core.email import send_image_request_email

from chromogenic.drivers.eucalyptus import ImageManager as EucaImageManager
from chromogenic.drivers.openstack import ImageManager as OSImageManager
from chromogenic.drivers.migration import KVM2Xen, Xen2KVM
from chromogenic.drivers.virtualbox import ExportManager

from django.conf import settings

@task(name='machine_export_task', ignore_result=False)
def machine_export_task(machine_export):
    logger.debug("machine_export_task task started at %s." % datetime.now())
    machine_export.status = 'processing'
    machine_export.save()

    local_download_dir = settings.LOCAL_STORAGE
    exp_provider = machine_export.instance.provider_machine.provider
    provider_type = exp_provider.type.name.lower()
    provider_creds = exp_provider.get_credentials()
    admin_creds = exp_provider.get_admin_identity().get_credentials()
    all_creds = {}
    all_creds.update(provider_creds)
    all_creds.update(admin_creds)
    manager = ExportManager(all_creds)
    #ExportManager().eucalyptus/openstack()
    if 'euca' in exp_provider:
        export_fn = manager.eucalyptus
    elif 'openstack' in exp_provider:
        export_fn = manager.openstack
    else:
        raise Exception("Unknown Provider %s, expected eucalyptus/openstack"
                        % (exp_provider, ))

    meta_name = manager.euca_img_manager._format_meta_name(
        machine_export.export_name,
        machine_export.export_owner.username,
        timestamp_str = machine_export.start_date.strftime('%m%d%Y_%H%M%S'))

    md5_sum, url = export_fn(machine_export.instance.provider_alias,
                             machine_export.export_name,
                             machine_export.export_owner.username,
                             download_dir=local_download_dir,
                             meta_name=meta_name)
    #TODO: Pass in kwargs (Like md5sum, url, etc. that are useful)
    # process_machine_export(machine_export, md5_sum=md5_sum, url=url)
    #TODO: Option to copy this file into iRODS
    #TODO: Option to upload this file into S3 

    logger.debug("machine_export_task task finished at %s." % datetime.now())
    return (md5_sum, url)

@task(name='machine_migration_task', ignore_result=False)
def machine_migration_task(origCls, orig_creds, migrateCls, migrate_creds, **imaging_args):
    #orig_creds = origCls._build_image_creds(orig_creds)
    orig = origCls(**orig_creds)
    #migrate_creds = migrateCls._build_image_creds(migrate_creds)
    migrate = migrateCls(**migrate_creds)
    #TODO: Select the correct migration class based on origCls && migrateCls
    #TODO: Pass orig_creds and migrate_creds to the correct migration class
    #TODO: Decide how to initialize manager for migrating..
    manager = orig

    #1. Download from orig
    download_kwargs = manager.parse_download_args(**imaging_args)
    download_location = manager.download_instance(**download_kwargs)

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
    new_image_id = migrate.upload_local_image(**upload_kwargs)
    return new_image_id

@task(name='machine_imaging_task', ignore_result=False)
def machine_imaging_task(managerCls, manager_creds, **create_img_args):
    manager = managerCls(**manager_creds)
    new_image_id = manager.create_image(**create_img_args)
    return new_image_id

