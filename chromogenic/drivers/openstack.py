"""
ImageManager:
    Remote Openstack Image management (Keystone, Nova, & Glance)

from chromogenic.drivers.openstack import ImageManager

credentials = {
    'username': '',
    'tenant_name': '',
    'password': '',
    'auth_url':'',
    'region_name':''
}
manager = ImageManager(**credentials)

manager.create_image('75fdfca4-d49d-4b2d-b919-a3297bc6d7ae', 'my new name')

"""
import os
import sys
import time
import logging
import string

from pytz import datetime
from rtwo.models.provider import OSProvider
from rtwo.models.identity import OSIdentity
from rtwo.driver import OSDriver
from rtwo.drivers.common import (
    _connect_to_keystone_v3, _connect_to_glance_by_auth, _connect_to_nova_by_auth,
    _connect_to_keystone, _connect_to_nova,
    _connect_to_glance, find
)

from chromogenic.drivers.base import BaseDriver
from chromogenic.common import run_command, wildcard_remove
from chromogenic.clean import mount_and_clean
from chromogenic.settings import chromo_settings
from keystoneclient.exceptions import NotFound
from glanceclient import exc as glance_exception
from glanceclient.common import progressbar
from glanceclient.common import utils

logger = logging.getLogger(__name__)

class ProgressHook(progressbar.VerboseIteratorWrapper):
    def __init__(self, wrapped, totalsize, hook=None, method='download'):
        self._wrapped = wrapped
        self._totalsize = float(totalsize)
        self._show_progress = self._totalsize != 0
        self._curr_size = 0
        self._curr_pct = 0
        self._last_update = -1
        self.hook = hook
        self.method = method

    def _display_progress_bar(self, size_read):
        if self._show_progress:
            self._curr_size += size_read
            self._curr_pct = round(int(100 * self._curr_size / self._totalsize))
            return self.log_current_progress()

    def log_current_progress(self):
        # Only log progress if a hook has been received
        if not getattr(self,'hook') or not hasattr(self.hook, 'on_update_status'):
            return
        if self._curr_pct == self._last_update:  #No repeat-updates
            return
        #if (self._curr_pct % 5 != 0):  # Slow down results to 0,5,10,...
        #   return
        self._last_update = self._curr_pct
        if self.method == 'download':
            self.hook.on_update_status("Downloading - %s" % self._curr_pct)
        elif self.method == 'upload':
            self.hook.on_update_status("Uploading - %s" % self._curr_pct)



class ImageManager(BaseDriver):
    """
    Convienence class that uses a combination of boto and euca2ools calls
    to remotely download an image from the cloud
    * See http://www.iplantcollaborative.org/Zku
      For more information on image management
    """
    glance = None
    nova = None
    keystone = None

    def keystone_tenants_method(self):
        """
        Pick appropriate version of keystone based on credentials
        """
        identity_version = self.creds.get('version', 'v2.0')

        if '3' in identity_version or identity_version == 3:
            return self.keystone.projects
        return self.keystone.tenants

    @classmethod
    def lc_driver_init(self, lc_driver, *args, **kwargs):
        lc_driver_args = {
            'username': lc_driver.key,
            'password': lc_driver.secret,
            'tenant_name': lc_driver._ex_tenant_name,
            'auth_url': lc_driver._ex_force_auth_url,
            'region_name': lc_driver._ex_force_service_region
        }
        lc_driver_args.update(kwargs)
        manager = ImageManager(*args, **lc_driver_args)
        return manager

    @classmethod
    def _build_image_creds(cls, credentials):
        """
        Credentials - dict()

        return the credentials required to build an "ImageManager"
        """
        img_args = credentials.copy()
        #Required:
        img_args['key']
        img_args['secret']
        img_args['ex_tenant_name']
        img_args['ex_project_name']
        img_args['auth_url']
        img_args['region_name']
        img_args['admin_url']

        return img_args

    @classmethod
    def _image_creds_convert(cls, *args, **kwargs):
        creds = kwargs.copy()
        key = creds.pop('key', None)
        secret = creds.pop('secret', None)
        tenant = creds.pop('ex_tenant_name', None)

        if not tenant:
            tenant = creds.pop('tenant_name', None)
        if not tenant:
            tenant = creds.pop('ex_project_name', None)
        if not tenant:
            tenant = creds.get('project_name')

        if tenant:
            creds['project_name'] = tenant

        creds.pop('location', None)
        creds.pop('router_name', None)
        if key and not creds.get('username'):
            creds['username'] = key
        if secret and not creds.get('password'):
            creds['password'] = secret
        auth_version = creds.get('ex_force_auth_version', '2.0_password')
        if '/v2.0' in creds['auth_url']:
            creds['auth_url'] = creds['auth_url'].replace('/tokens','')
        elif '2' in auth_version:
            creds['auth_url'] += "/v2.0/"
            creds['version'] = 'v2.0'
        elif '3' in auth_version:
            creds['version'] = 'v3'
            creds['project_name'] = tenant
        return creds

    def __init__(self, *args, **kwargs):
        if len(args) == 0 and len(kwargs) == 0:
            raise KeyError("Credentials missing in __init__. ")

        admin_args = kwargs.copy()
        auth_version = kwargs.get('ex_force_auth_version','2.0_password')
        if '2' in auth_version:
            if '/v2.0/tokens' not in admin_args['auth_url']:
                admin_args['auth_url'] += '/v2.0/tokens'
        self.admin_driver = self._build_admin_driver(**admin_args)
        self.creds = self._image_creds_convert(*args, **kwargs)
        (self.keystone,\
            self.nova,\
            self.glance) = self._new_connection(*args, **self.creds)

    def _parse_download_location(self, server, image_name, **kwargs):
        download_location = kwargs.get('download_location')
        download_dir = kwargs.get('download_dir')
        identity_version = self.creds.get('version','v2.0')
        list_args = {}
        if '3' in identity_version:
            domain_id = kwargs.pop('domain', 'default')
            list_args['domain_id'] = domain_id
        if not download_dir and not download_location:
            raise Exception("Could not parse download location. Expected "
                            "'download_dir' or 'download_location'")
        elif not download_location:
            #Use download dir & tenant_name to keep filesystem order
            tenant = find(self.keystone_tenants_method(), id=server.tenant_id, **list_args)
            local_user_dir = os.path.join(download_dir, tenant.name)
            if not os.path.exists(os.path.dirname(local_user_dir)):
                os.makedirs(local_user_dir)
            download_location = os.path.join(
                local_user_dir, '%s.qcow2' % self.clean_path(image_name))
        elif not download_dir:
            download_dir = os.path.dirname(download_location)
        return download_dir, download_location

    def clean_path(self, image_name):
        valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
        return ''.join(ch for ch in image_name if ch in valid_chars)

    def download_instance_args(self, instance_id, image_name='', **kwargs):
        #Step 0: Is the instance alive?
        server = self.get_server(instance_id)
        if not server and not kwargs.get('download_location'):
            raise Exception("Instance %s does not exist -- download_location required to continue!" % instance_id)


        #Set download location
        download_dir, download_location = self._parse_download_location(server, image_name, **kwargs)
        download_args = {
                'snapshot_id': kwargs.get('snapshot_id'),
                'instance_id': instance_id,
                'download_dir' : download_dir,
                'download_location' : download_location,
        }
        return download_args

    def download_instance(self, instance_id, download_location='/tmp', **kwargs):
        snapshot_id=kwargs.get('snapshot_id',None)
        if snapshot_id:
            snapshot_id, download_location = self.download_snapshot(snapshot_id, download_location)
        else:
            snapshot_id, download_location = self._download_instance(instance_id, download_location)
        return snapshot_id, download_location

    def create_image(self, instance_id, image_name, *args, **kwargs):
        """
        Creates an image of a running instance
        Required Args:
            instance_id - The instance that will be imaged
            image_name - The name of the image
            download_location OR download_dir - Where to download the image
            if download_dir:
                download_location = download_dir/username/image_name.qcow2
        """
        #Step 1: Retrieve a copy of the instance ( Use snapshot_id if given )
        download_kwargs = self.download_instance_args(instance_id, image_name, **kwargs)
        snapshot_id, download_location = self.download_instance(**download_kwargs)
        download_dir = os.path.dirname(download_location)
	#Step 2: Turn the snapshot into a 'formal image'
        kwargs.pop('download_dir',None)
        kwargs.pop('download_location',None)
        return self.clone_image(snapshot_id, image_name, download_dir, download_location, **kwargs)

    def clone_image(self, parent_image_id, image_name, download_dir, download_location, **kwargs):
	"""
	Creates an image of an image in the image-list
        Required Args:
            parent_image_id - The parent image that will be cloned
            image_name - The name of the new image
            download_location OR download_dir - Where to download the image
            if download_dir:
                download_location = download_dir/username/image_name.qcow2
	"""
        parent_image = self.get_image(parent_image_id)
        #Step 1 download a local copy
        if not os.path.exists(download_location) or kwargs.get('force',False):
            self.download_image(parent_image_id, download_location)

        #Step 2: Clean the local copy
        if kwargs.get('clean_image',True):
            mount_and_clean(
                    download_location,
                    os.path.join(download_dir, 'mount/'),
                    status_hook=getattr(self, 'hook', None),
                    method_hook=getattr(self, 'clean_hook',None),
                    **kwargs)

        #Step 3: Upload the local copy as a 'real' image
        # with seperate kernel & ramdisk
        if kwargs.get('upload_image',True):
            if hasattr(parent_image, 'properties'):  # Treated as an obj.
                properties = parent_image.properties
                properties.update({
                    'container_format': parent_image.container_format,
                    'disk_format': parent_image.disk_format,
                })
            elif hasattr(parent_image, 'items'):  # Treated as a dict.
                properties = dict(parent_image.items())
            upload_args = self.parse_upload_args(image_name, download_location,
                                                 kernel_id=properties.get('kernel_id'),
                                                 ramdisk_id=properties.get('ramdisk_id'),
                                                 disk_format=properties.get('disk_format'),
                                                 container_format=properties.get('container_format'),
                                                 **kwargs)
            new_image = self.upload_local_image(**upload_args)

        if kwargs.get('remove_local_image', True):
            wildcard_remove(download_dir)

        if kwargs.get('remove_image', False):
            wildcard_remove(download_dir)
            try:
                self.delete_images(image_id=parent_image.id)
            except Exception as exc:
                logger.exception("Could not delete the image %s - %s" % (parent_image.id, exc.message))

        return new_image

    def parse_upload_args(self, image_name, image_path, **kwargs):
        """
        Use this function when converting 'create_image' args to
        'upload_local_image' args
        """
        if kwargs.get('kernel_id') and kwargs.get('ramdisk_id'):
            #Both kernel_id && ramdisk_id
            #Prepare for upload_local_image()
            return self._parse_args_upload_local_image(image_name,
                                                  image_path,
                                                  **kwargs)
        elif kwargs.get('kernel_path') and kwargs.get('ramdisk_path'):
            #Both kernel_path && ramdisk_path
            #Prepare for upload_full_image()
            return self._parse_args_upload_full_image(image_name,
                    image_path, **kwargs)
        #one path and one id OR no path no id
        else:
            #Image does not need a kernel/ramdisk and runs entirely on its own.
            return self._parse_args_upload_local_image(
                image_name, image_path, **kwargs)

    def _parse_args_upload_full_image(self, image_name,
                                      image_path, **kwargs):
        upload_args = {
            'image_name':image_name,
            'image_path':image_path,
            'kernel_path':kwargs['kernel_path'],
            'ramdisk_path':kwargs['ramdisk_path'],
            'is_public':kwargs.get('public',True),
        }
        return upload_args

    def _parse_args_upload_local_image(self, image_name,
                                       image_path, **kwargs):
        upload_args = {
             'image_path':image_path,
             'image_name':image_name,
             'disk_format':kwargs.get('disk_format', 'ami'),
             'container_format':kwargs.get('container_format','ami'),
             'private_user_list':kwargs.get('private_user_list', []),
        }
        if kwargs.get('public') and not kwargs.get('visibility'):
            upload_args['visibility'] = \
                "public" if kwargs.get('public', True) else "private"
        elif not kwargs.get('visibility'):
            raise ValueError("Missing kwarg 'visibility'")
        if kwargs.get('kernel_id') and kwargs.get('ramdisk_id'):
            upload_args.update({
                'kernel_id':  kwargs['kernel_id'],
                'ramdisk_id': kwargs['ramdisk_id']
            })

        # This hook allows you to add arbitrary metadata key-values (Static, for now)
        # directly to the upload args.
        # A future solution might expect a method to pass 'upload_args' for further manipulation..
        included_metadata = getattr(chromo_settings, "INCLUDE_METADATA", {})
        if included_metadata and type(included_metadata) == dict:
            upload_args.update(included_metadata)
        return upload_args

    def download_snapshot(self, snapshot_id, download_location, *args, **kwargs):
        """
        Download an existing snapshot to local download directory
        Required Args:
            snapshot_id - The snapshot ID to be downloaded (1234-4321-1234)
            download_location - The exact path where image will be downloaded
        """
        #Step 1: Find snapshot by id
        return (snapshot_id,
                self.download_image(snapshot_id, download_location))


    def _download_instance(self, instance_id, download_location, *args, **kwargs):
        """
        Download an existing instance to local download directory
        Required Args:
            instance_id - The instance ID to be downloaded (1234-4321-1234)
            download_location - The exact path where image will be downloaded

        NOTE: It is recommended that you 'prepare the snapshot' before creating
        an image by running 'sync' and 'freeze' on the instance. See
        http://docs.openstack.org/grizzly/openstack-ops/content/snapsnots.html#consistent_snapshots
        """
        #Step 2: Create local path for copying image
        server = self.get_server(instance_id)
        if server:
            identity_version = self.creds.get('version','v2.0')
            list_args = {}
            if '3' in identity_version:
                domain_id = kwargs.pop('domain', 'default')
                list_args['domain_id'] = domain_id
            tenant = find(self.keystone_tenants_method(), id=server.tenant_id, **list_args)
        else:
            tenant = None
        ss_prefix = kwargs.get('ss_prefix',
                'ChromoSnapShot_%s' % instance_id) #Legacy format
        snapshot = self.find_image(ss_prefix, contains=True)
        if snapshot:
            snapshot = snapshot[0]
            logger.info("Found snapshot %s. " % snapshot.id)
            if os.path.exists(download_location) and snapshot.size <= os.path.getsize(download_location):
                logger.info("Download should be valid, returning snapshot+location")
                return (snapshot.id, download_location)
            if getattr(self,'hook') and hasattr(self.hook, 'on_update_status'):
                self.hook.on_update_status("Downloading Snapshot:%s" % (snapshot.id,))
            logger.info("Downloading from existing snapshot: %s" % (snapshot.id,))
            return (snapshot.id,
                    self.download_image(snapshot.id, download_location))

        now = kwargs.get('timestamp',datetime.datetime.now()) # Pytz datetime
        now_str = now.strftime('%Y-%m-%d_%H:%M:%S')
        ss_name = '%s_%s' % (ss_prefix, now_str)
        meta_data = {}
        if getattr(self,'hook') and hasattr(self.hook, 'on_update_status'):
            self.hook.on_update_status("Creating Snapshot:%s from Instance:%s" % (ss_name, instance_id))
        logger.info("Creating snapshot from instance %s. " % instance_id)
        snapshot = self.create_snapshot(instance_id, ss_name, delay=True, **meta_data)
        return (snapshot.id,
                self.download_image(snapshot.id, download_location))

    def download_image_args(self, image_id, **kwargs):
        download_dir= kwargs.get('download_dir','/tmp')

        image = self.get_image(image_id)
        if image.container_format == 'ami':
            ext = 'img'
        elif image.container_foramt == 'qcow':
            ext = 'qcow2'
        # Create our own sub-system inside the chosen directory
        # <dir>/<image_id>
        # This helps us keep track of ... everything
        download_location = os.path.join(
                download_dir,
                image_id,
                "%s.%s" % (image.name, ext))
        download_args = {
                'snapshot_id': kwargs.get('snapshot_id'),
                'instance_id': instance_id,
                'download_dir' : download_dir,
                'download_location' : download_location,
        }
        return download_args

    def download_image(self, image_id, download_location):
        if os.path.exists(download_location):
            return download_location
        return self._perform_download(image_id, download_location)

    def _perform_download(self, image_id, download_location):
        return self._perform_api_download(image_id, download_location)

    def _perform_api_download(self, image_id, download_location, hook=None):
        if hook and not hasattr(self,'hook'):
            self.hook = hook
        image = self.get_image(image_id)
        #Step 2: Download local copy of snapshot
        logger.info("Downloading Image %s: %s" % (image_id, download_location))
        if not os.path.exists(os.path.dirname(download_location)):
            os.makedirs(os.path.dirname(download_location))
        with open(download_location,'wb') as f:
            body = self.glance.images.data(image_id)
            body = ProgressHook(body, len(body), getattr(self, 'hook'), 'download')
            for chunk in body:
                f.write(chunk)
        if body._totalsize != body._curr_size:
            raise Exception("Image Download Failed! Current Size %s/%s" % (body._curr_size, body._totalsize))
        logger.info("Download Image %s Completed: %s" % (image_id, download_location))
        return download_location

    def upload_image(self, image_name, image_path, **upload_args):
        if upload_args.get('kernel_path') and upload_args.get('ramdisk_path'):
            return self.upload_full_image(image_name, image_path, **upload_args)
        else:
            return self.upload_local_image(image_name, image_path, **upload_args)

    def upload_local_image(self, image_name, image_path,
                     container_format='ovf',
                     disk_format='raw',
                     is_public=True, private_user_list=[], **extras):
        """
        Upload a single file as a glance image
        'extras' kwargs will be passed directly to glance.
        """
        logger.info("Creating new image %s - %s" % (image_name, container_format))
        new_image = self.glance.images.create(
            name=image_name,
            container_format=container_format,
            disk_format=disk_format,
            visibility="public" if is_public else "private",
            **extras)
        logger.info("Uploading file to newly created image %s - %s" % (new_image.id, image_path))
        if getattr(self,'hook') and hasattr(self.hook, 'on_update_status'):
            self.hook.on_update_status("Uploading file to image %s" % new_image.id)
        data_file = open(image_path, 'rb')
        filesize = utils.get_file_size(data_file)
        body = ProgressHook(data_file, filesize, getattr(self, 'hook'), 'upload')

        self.glance.images.upload(new_image.id, data_file)
        # ASSERT: New image ID now that 'the_file' has completed the upload
        logger.info("New image created: %s - %s" % (image_name, new_image.id))
        for tenant_name in private_user_list:
            self.share_image(new_image,tenant_name)
            logger.info("%s has permission to launch %s"
                         % (tenant_name, new_image))
        return new_image.id

    def upload_full_image(self, image_name, image_path,
                          kernel_path, ramdisk_path, is_public=True,
                          private_user_list=[]):
        """
        Upload a full image to glance..
            name - Name of image when uploaded to OpenStack
            image_path - Path containing the image file
            kernel_path - Path containing the kernel file
            ramdisk_path - Path containing the ramdisk file
        Requires 3 separate filepaths to uploads the Ramdisk, Kernel, and Image
        This is useful for migrating from Eucalyptus/AWS --> Openstack
        """
        new_kernel = self.upload_local_image('eki-%s' % image_name,
                                             kernel_path,
                                             container_format='aki',
                                             disk_format='aki',
                                             is_public=is_public)
        new_ramdisk = self.upload_local_image('eri-%s' % image_name,
                                             ramdisk_path,
                                             container_format='ari',
                                             disk_format='ari',
                                             is_public=is_public)
        opts = {
            'kernel_id' : new_kernel,
            'ramdisk_id' : new_ramdisk
        }
        new_image = self.upload_local_image(image_name, image_path,
                                             container_format='ami',
                                             disk_format='ami',
                                             is_public=is_public,
                                             properties=opts)
        for tenant_name in private_user_list:
            self.share_image(new_kernel,tenant_name)
            self.share_image(new_ramdisk,tenant_name)
            self.share_image(new_image,tenant_name)
            logger.debug("%s has permission to launch %s"
                         % (tenant_name, new_image))
        return new_image

    def delete_images(self, image_id=None, image_name=None):
        if not image_id and not image_name:
            raise Exception("delete_image expects image_name or image_id as keyword"
            " argument")

        if image_name:
            images = [img for img in self.admin_list_images()
                      if image_name in img.name]
        elif image_id:
            images = [self.get_image(image_id)]

        if len(images) == 0:
            return False
        for image in images:
            self.glance.images.delete(image.id)

        return True

    # Public methods that are OPENSTACK specific

    def create_snapshot(self, instance_id, name, delay=False, **kwargs):
        """
        NOTE: It is recommended that you 'prepare the snapshot' before creating
        an image by running 'sync' and 'freeze' on the instance. See
        http://docs.openstack.org/grizzly/openstack-ops/content/snapsnots.html#consistent_snapshots
        """
        metadata = kwargs
        server = self.get_server(instance_id)
        if not server:
            raise Exception("Server %s does not exist" % instance_id)
        logger.debug("Instance is prepared to create a snapshot")
        snapshot_id = self.nova.servers.create_image(server, name, metadata)
        if getattr(self,'hook') and hasattr(self.hook, 'on_update_status'):
            self.hook.on_update_status("Retrieving Snapshot:%s created from Instance:%s" % (snapshot_id, instance_id))
        snapshot = self.get_image(snapshot_id)
        if not delay:
            return snapshot
        #NOTE: Default behavior returns snapshot upon creation receipt.
        # In some cases (celery) it is better to wait until snapshot is completed.
        return self.retrieve_snapshot(snapshot_id)

    def retrieve_snapshot(self, snapshot_id, timeout=160):
        #Step 2: Wait (Exponentially) until status moves from:
        # queued --> saving --> active
        attempts = 0
        logger.debug("Attempting to retrieve Snapshot %s" % (snapshot_id,))
        while True:
            try:
                snapshot = self.get_image(snapshot_id)
            except glance_exception.HTTPUnauthorized:
                raise Exception("Cannot contact glance to retrieve snapshot - %s" % snapshot_id)
            if snapshot:
                sstatus = snapshot.status
            else:
                sstatus = "missing"

            if attempts >= timeout:
                break
            if sstatus in ["active","failed"]:
                break

            attempts += 1
            logger.debug("Snapshot %s in non-active state %s" % (snapshot_id, sstatus))
            logger.debug("Attempt:%s, wait 1 minute" % attempts)
            time.sleep(60)
        if not snapshot:
            raise Exception("Retrieve_snapshot Failed. No ImageID %s" % snapshot_id)
        if sstatus not in 'active':
            logger.warn("Retrieve_snapshot timeout exceeded %sm. Final status was %s" % (timeout,sstatus))

        return snapshot



    # Private methods and helpers
    def _read_file_type(self, local_image):
        out, _ = run_command(['file', local_image])
        logger.info("FileOutput: %s" % out)
        if 'qemu qcow' in out.lower():
            if 'v2' in out.lower():
                return 'qcow2'
            else:
                return 'qcow'
        elif 'Linux rev 1.0' in out.lower() and 'ext' in out.lower():
            return 'img'
        else:
            raise Exception("Could not guess the type of file. Output=%s"
                            % out)


    def _admin_identity_creds(self, **kwargs):
        creds = {}
        creds['key'] = kwargs.get('username')
        creds['secret'] = kwargs.get('password')
        creds['ex_tenant_name'] = kwargs.get('tenant_name')
        creds['ex_project_name'] = kwargs.get('project_name')
        return creds

    def _admin_driver_creds(self, **kwargs):
        creds = {}
        creds['region_name'] = kwargs.get('region_name')
        creds['router_name'] = kwargs.get('router_name')
        creds['admin_url'] = kwargs.get('admin_url')
        creds['ex_force_auth_url'] = kwargs.get('auth_url')
        if 'ex_force_auth_version' not in kwargs and 'v3' in kwargs.get('auth_url',''):
            creds['ex_force_auth_version'] = '3.x_password'
        elif 'ex_force_auth_version' not in kwargs or 'v2.0' in kwargs.get('auth_url',''):
            creds['ex_force_auth_version'] = '2.0_password'
        else:
            creds['ex_force_auth_version'] = '3.x_password' # Default, explicitly stated.

        return creds

    def _build_admin_driver(self, **kwargs):
        #Set Meta
        OSProvider.set_meta()
        #TODO: Set location from kwargs
        provider = OSProvider(identifier=kwargs.get('location'))
        admin_creds = self._admin_identity_creds(**kwargs)
        #logger.info("ADMINID Creds:%s" % admin_creds)
        identity = OSIdentity(provider, **admin_creds)
        driver_creds = self._admin_driver_creds(**kwargs)
        #logger.info("ADMINDriver Creds:%s" % driver_creds)
        admin_driver = OSDriver(provider, identity, **driver_creds)
        return admin_driver

    def _new_connection(self, *args, **kwargs):
        """
        Can be used to establish a new connection for all clients
        """
        version = kwargs.get('version')
        if version == 'v3':
            (auth, sess, token) = _connect_to_keystone_v3(**kwargs)
            keystone = _connect_to_keystone(auth=auth, session=sess, version=version)
            nova = _connect_to_nova_by_auth(auth=auth, session=sess)
            glance = _connect_to_glance_by_auth(auth=auth, session=sess)
        else:
            ks_kwargs = self._build_keystone_creds(kwargs)
            nova_kwargs = self._build_nova_creds(kwargs)
            keystone = _connect_to_keystone(*args, **ks_kwargs)
            nova = _connect_to_nova(*args, **nova_kwargs)
            glance = _connect_to_glance(keystone, *args, **kwargs)
        return (keystone, nova, glance)

    def _build_nova_creds(self, credentials):
        nova_args = credentials.copy()
        #HACK - Nova is certified-broken-on-v3. 
        nova_args['version'] = 'v2.0'
        nova_args['auth_url'] = nova_args['auth_url'].replace('v3','v2.0').replace('/tokens','')
        if credentials.get('ex_force_auth_version','3.x_password') == '2.0_password':
            nova_args['tenant_name'] = credentials.get('project_name')
        return nova_args

    def _build_keystone_creds(self, credentials):
        ks_args = credentials.copy()
        auth_version = ks_args.get('version', 'v3')
        ks_version = ks_args.get('ex_force_auth_version', '3.x_password')
        ks_args['auth_url'] = ks_args['auth_url'].replace('/v2.0','').replace('/v3','').replace('/tokens','')
        if 'project_name' not in ks_args:
            ks_args['project_name'] = ks_args.get('tenant_name','')
        if ks_version == '3.x_password':
            ks_args['auth_url'] += '/v3'
        elif ks_version == '2.0_password':
            ks_args['auth_url'] += '/v2.0'
        #Graceful degredation -- use project_name over tenant_name, tenant_name over username.
        ks_args['project_name'] = ks_args.get('ex_tenant_name', ks_args.get('ex_project_name', ks_args.get('username', None)))
        return ks_args

    def get_instance(self, instance_id):
        instances = self.admin_driver._connection.ex_list_all_instances()
        for inst in instances:
            if inst.id == instance_id:
                return inst
        return None

    def get_server(self, server_id):
        servers = [server for server in
                self.nova.servers.list(search_opts={'all_tenants':1}) if
                server.id == server_id]
        if not servers:
            return None
        return servers[0]

    def list_nova_images(self):
        return self.nova.images.list()

    def get_image_by_name(self, name):
        for img in self.admin_list_images():
            if img.name == name:
                return img
        return None

    #Image sharing
    def shared_images_for(self, tenant_name=None,
                          image_name=None, image_id=None):
        """
        #NOTE: Returns a GENERATOR not a list. (So -- Failures here will PASS silently!)
        """
        if tenant_name:
            raise KeyError("Key tenant_name has been deprecated in latest version of glance.image_members -- If you need this -- Contact a programmer!")
        if image_id:
            image = self.glance.images.get(image_id)
            if hasattr(image, 'visibility'):  # Treated as an obj.
                visibility = image.visibility
            elif hasattr(image, 'items'):  # Treated as a dict.
                visibility = image['visibility']
            else:
                raise Exception(
                    "Could not parse visibility for a glance image!"
                    " Ask a programmer for help!")
            if visibility == 'public':
                return []
            return self.glance.image_members.list(image_id)
        if image_name:
            image = self.find_image(image_name)

            if type(image) == list:
                image = image[0]

            if hasattr(image, 'visibility'):  # Treated as an obj.
                visibility = image.visibility
            elif hasattr(image, 'items'):  # Treated as a dict.
                visibility = image['visibility']
            else:
                raise Exception(
                    "Could not parse visibility for a glance image!"
                    " Ask a programmer for help!")

            if visibility == 'public':
                return []

            return self.glance.image_members.list(image.id)

    def share_image(self, image, tenant_name, **kwargs):
        """
        Share an image with tenant_name
        """
        identity_version = self.creds.get('version','v2.0')
        list_args = {}
        if '3' in identity_version:
            domain_id = kwargs.pop('domain', 'default')
            list_args['domain_id'] = domain_id
        tenant = self.find_tenant(tenant_name, **list_args)
        if not tenant:
            raise Exception("No tenant named %s" % tenant_name)
        return self.glance.image_members.create(image.id, tenant.id)

    def unshare_image(self, image, tenant_name, **kwargs):
        """
        Remove a shared image with tenant_name
        """
        identity_version = self.creds.get('version','v2.0')
        list_args = {}
        if '3' in identity_version:
            domain_id = kwargs.pop('domain', 'default')
            list_args['domain_id'] = domain_id
        tenant = find(self.keystone_tenants_method(), name=tenant_name, **list_args)
        return self.glance.image_members.delete(image.id, tenant.id)

    #Alternative image uploading

    #Lists
    def update_image(self, image, **kwargs):
        image_update = 'v3'
        if hasattr(image, 'properties'):  # Treated as an obj.
            properties = image.properties
            image_update = 'v2'
        elif hasattr(image, 'items'):  # Treated as a dict.
            image_update = 'v3'
            properties = dict(image.items())

        if 'properties' not in kwargs:
            if image_update == 'v2':
                properties = image.properties
            elif image_update == 'v3':
                properties = image.get('properties')
        else:
            properties = kwargs.pop("properties")

        if image_update == 'v2':
            image.update(properties=properties, **kwargs)
        elif image_update == 'v3':
            self.glance.images.update(image.id, **kwargs)
        #After the update, change reference to new image with updated vals
        return self.get_image(image.id)

    def admin_list_images(self, **kwargs):
        """
        Treats 'is_public' as a 3-way switch:
          None = Public and Private as seen by this account
          True = Public images ONLY
         False = Private images ONLY
        """
        # NOTE: now that glance has moved away from is_public
        # this 'feature' may not be necessary.
        is_public = None
        if 'is_public' in kwargs:
            is_public = kwargs.pop('is_public')
        return self.list_images(is_public=is_public, **kwargs)

    def list_images(self, **kwargs):
        """
        These images have an update() function
        to update attributes like public/private, min_disk, min_ram

        NOTE: glance.images.list() returns a generator, we return lists
        """
        return [img for img in self.glance.images.list(**kwargs)]

    #Finds
    def get_image(self, image_id):
        return self.glance.images.get(image_id)

    def find_images(self, image_name, contains=False):
        return self.find_image(image_name, contains=contains)

    def find_image(self, image_name, contains=False):
        return [i for i in self.admin_list_images() if
                ( i.name and i.name.lower() == image_name.lower() )
                or (contains and i.name and image_name.lower() in i.name.lower())]

    def find_tenant(self, tenant_name, **kwargs):
        try:
            identity_version = self.creds.get('version','v2.0')
            list_args = {}
            if '3' in identity_version:
                domain_id = kwargs.pop('domain', 'default')
                list_args['domain_id'] = domain_id
            tenant = find(self.keystone_tenants_method(), name=tenant_name, **list_args)
            return tenant
        except NotFound:
            return None
