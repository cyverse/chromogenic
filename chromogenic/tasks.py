from datetime import datetime

from celery.decorators import task

from threepio import logger

from chromogenic.migrate import migrate_instance
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

@task(name='migrate_instance_task', ignore_result=False)
def migrate_instance_task(origCls, orig_creds, migrateCls, migrate_creds, **imaging_args):
    new_image_id = migrate_instance(origCls, orig_creds,
                     migrateCls, migrate_creds,
                     **imaging_args)
    return new_image_id

@task(name='machine_imaging_task', ignore_result=False)
def machine_imaging_task(managerCls, manager_creds, **create_img_args):
    manager = managerCls(**manager_creds)
    new_image_id = manager.create_image(**create_img_args)
    return new_image_id

