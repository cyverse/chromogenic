import re

from datetime import datetime

from celery.decorators import task

from threepio import logger

from core.email import send_image_request_email
from core.models.machine_request import process_machine_request

from chromogenic.drivers.eucalyptus import ImageManager as EucaImageManager
from chromogenic.drivers.openstack import ImageManager as OSImageManager
from chromogenic.drivers.migration import EucaOSMigrater
from chromogenic.drivers.virtualbox import ExportManager

from django.conf import settings

@task()
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
    process_machine_export(machine_export, md5_sum=md5_sum, url=url)
    #TODO: Option to copy this file into iRODS
    #TODO: Option to upload this file into S3 
    #TODO: send an email with instructions on how/where to go from here

    logger.debug("machine_export_task task finished at %s." % datetime.now())
    pass

@task(name='machine_imaging_task', ignore_result=True)
def machine_imaging_task(machine_request, provider_creds, migrate_creds):
    try:
        machine_request.status = 'processing'
        machine_request.save()
        logger.debug('%s' % machine_request)
        local_download_dir = settings.LOCAL_STORAGE
        new_image_id = select_and_build_image(machine_request,
                provider_creds, migrate_creds, local_download_dir)
        if new_image_id is None:
            raise Exception('The image cannot be built as requested. '
                            + 'The provider combination is probably bad.')
        logger.info('New image created - %s' % new_image_id)
        return new_image_id
    except Exception as e:
        logger.exception(e)
        machine_request.status = 'error - %s' % (e,)
        machine_request.save()
        return None

def select_and_build_image(machine_request, provider_creds,
                           migrate_creds, local_download_dir='/tmp'):
    """
    Directing traffic between providers
    Fill out all available fields using machine request data
    """

    old_provider = machine_request.parent_machine.provider
    new_provider = machine_request.new_machine_provider
    old_type = old_provider.type.name.lower()
    new_type = new_provider.type.name.lower()
    new_image_id = None
    logger.info('Processing machine request to create a %s image from a %s '
                'instance' % (new_provider, old_provider))
    
    if old_type == 'eucalyptus':
        if new_type == 'eucalyptus':
            credentials = EucaImageManager._build_image_creds(provider_creds)
            manager = EucaImageManager(**credentials)
            #Rebuild meta information based on machine_request
            meta_name = '%s_%s_%s_%s' % ('admin',
                machine_request.new_machine_owner.username,
                machine_request.new_machine_name.replace(
                    ' ','_').replace('/','-'),
                machine_request.start_date.strftime('%m%d%Y_%H%M%S'))
            public_image = "public" in machine_request.new_machine_visibility\
                                        .lower()
            private_user_list=re.split(', | |\n', machine_request.access_list)
            exclude=re.split(", | |\n", machine_request.exclude_files)
            #Create image on image manager
            new_image_id = manager.create_image(
                machine_request.instance.provider_alias,
                image_name=machine_request.new_machine_name,
                public=public_image,
                #Split the string by ", " OR " " OR "\n" to create the list
                private_user_list=private_user_list,
                exclude=exclude,
                meta_name=meta_name,
                local_download_dir=local_download_dir,
            )
        elif new_type == 'openstack':
            logger.info('Create openstack image from euca image')
            euca_credentials = EucaImageManager._build_image_creds(provider_creds)
            euca_manager = EucaImageManager(**euca_credentials)
            os_credentials = OSImageManager._build_image_creds(migrate_creds)
            os_manager = OSImageManager(**os_credentials)
            manager = EucaOSMigrater(euca_manager, os_manager)
            new_image_id = manager.migrate_instance(
                machine_request.instance.provider_alias,
                machine_request.new_machine_name,
                local_download_dir=local_download_dir) 
    elif old_type == 'openstack':
        if new_type == 'eucalyptus':
            logger.info('Create euca image from openstack image')
            #TODO: Replace with OSEucaMigrater when this feature is complete
            new_image_id = None
        elif new_type == 'openstack':
            logger.info('Create openstack image from openstack image')
            os_credentials = OSImageManager._build_image_creds(provider_creds)
            manager = OSImageManager(**os_credentials)
            #TODO: When switching between OS Providers (OS-->Devstack?)
            new_image_id = manager.create_image(
                machine_request.instance.provider_alias,
                machine_request.new_machine_name,
                local_download_dir=local_download_dir)
            #TODO: Grab the machine, then add image metadata here
            machine = [img for img in manager.list_images()
                       if img.id == new_image_id]
            if not machine:
                return
    return new_image_id

