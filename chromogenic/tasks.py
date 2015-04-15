import logging
from datetime import datetime

from celery.decorators import task

from chromogenic.migrate import migrate_instance
from chromogenic.export import export_instance
from chromogenic.drivers.virtualbox import ImageManager as VBoxManager

logger = logging.getLogger(__name__)

@task(name='instance_export_task', queue="imaging", ignore_result=False)
def instance_export_task(instance_export):
    logger.info("instance_export_task task started at %s." % datetime.now())
    instance_export.status = 'processing'
    instance_export.save()


    (orig_managerCls, orig_creds,
     export_managerCls, export_creds) = instance_export.prepare_manager()
    manager = VBoxManager(**export_creds)

    meta_name = manager._format_meta_name(
        instance_export.export_name,
        instance_export.export_owner.username,
        timestamp_str = instance_export.start_date.strftime('%m%d%Y_%H%M%S'))

    file_loc, md5_sum = export_instance(orig_managerCls, orig_creds,
                                     export_managerCls, export_creds)

    logger.info("instance_export_task task finished at %s." % datetime.now())
    return (file_loc, md5_sum)


@task(name='migrate_instance_task', queue="imaging", ignore_result=False)
def migrate_instance_task(origCls, orig_creds, migrateCls, migrate_creds, **imaging_args):
    logger.info("migrate_instance_task task started at %s." % datetime.now())
    new_image_id = migrate_instance(origCls, orig_creds,
                     migrateCls, migrate_creds,
                     **imaging_args)
    logger.info("migrate_instance_task task finished at %s." % datetime.now())
    return new_image_id

@task(name='machine_imaging_task', queue="imaging", ignore_result=False)
def machine_imaging_task(managerCls, manager_creds, create_img_args):
    logger.info("machine_imaging_task task started at %s." % datetime.now())
    manager = managerCls(**manager_creds)
    new_image_id = manager.create_image(**create_img_args)
    logger.info("machine_imaging_task task finished at %s." % datetime.now())
    return new_image_id

