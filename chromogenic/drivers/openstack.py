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
import time

from threepio import logger

from rtwo.provider import OSProvider
from rtwo.identity import OSIdentity
from rtwo.driver import OSDriver
from rtwo.drivers.common import _connect_to_keystone, _connect_to_nova,\
                                   _connect_to_glance, find

from service.deploy import freeze_instance, sync_instance
from service.tasks.driver import deploy_to
from chromogenic.drivers.base import BaseDriver
from chromogenic.common import run_command, wildcard_remove
from chromogenic.clean import remove_user_data, remove_atmo_data,\
                                  remove_vm_specific_data
from chromogenic.common import unmount_image, mount_image, remove_files,\
                                    fsck_qcow, get_latest_ramdisk
from keystoneclient.exceptions import NotFound

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
        #Ignored:
        #img_args.pop('admin_url', None)
        #img_args.pop('router_name', None)
        #img_args.pop('ex_project_name', None)

        return img_args

    @classmethod
    def _image_creds_convert(cls, *args, **kwargs):
        creds = kwargs.copy()
        key = creds.pop('key', None)
        secret = creds.pop('secret', None)
        tenant = creds.pop('ex_tenant_name', None)
        creds.pop('ex_project_name', None)
        creds.pop('router_name', None)
        creds.pop('admin_url', None)
        if key and not creds.get('username'):
            creds['username'] = key
        if secret and not creds.get('password'):
            creds['password'] = secret
        if tenant and not creds.get('tenant_name'):
            creds['tenant_name'] = tenant
        return creds

    def __init__(self, *args, **kwargs):
        if len(args) == 0 and len(kwargs) == 0:
            raise KeyError("Credentials missing in __init__. ")

        self.admin_driver = self._build_admin_driver(**kwargs)
        creds = self._image_creds_convert(*args, **kwargs)
        (self.keystone,\
            self.nova,\
            self.glance) = self._new_connection(*args, **creds)

    def create_image(self, instance_id, image_name,
                     **kwargs):
        #Step 1: Create a local copy of the instance via snapshot
        (download_dir, download_location, snapshot) = self.download_instance(
                instance_id, image_name,
                download_dir=kwargs.get('download_dir'),
                snapshot_id=kwargs.get('snapshot_id'))

        #Step 2: Clean the local copy
        fsck_qcow(download_location)
        if kwargs.get('clean_image',True):
            self.mount_and_clean(
                    download_location,
                    os.path.join(download_dir, 'mount/'),
                    **kwargs=kwargs)

        #Step 3: Upload the local copy as a 'real' image
        # with seperate kernel & ramdisk
        prev_kernel = snapshot.properties['kernel_id']
        prev_ramdisk = snapshot.properties['ramdisk_id']
        new_image = self.upload_local_image(download_location, image_name, 'ami', 'ami', True, {
            'kernel_id': prev_kernel,
            'ramdisk_id': prev_ramdisk})
        #Step 6: Delete the snapshot
        snapshot.delete()
        return new_image.id

    def download_instance(self, instance_id, image_name,
                          download_dir='/tmp',
                          snapshot_id=None):
        """
        NOTE: It is recommended that you 'prepare the snapshot' before creating
        an image by running 'sync' and 'freeze' on the instance. See
        http://docs.openstack.org/grizzly/openstack-ops/content/snapsnots.html#consistent_snapshots
        """
        #Step 0: Is the instance alive?
        server = self.get_server(instance_id)
        if not server:
            raise Exception("Instance %s does not exist" % instance_id)

        #Step 1: If not snapshot_id, create new snapshot
        if not snapshot_id:
            ss_name = 'TEMP_SNAPSHOT <%s>' % image_name
            snapshot = self.create_snapshot(instance_id, ss_name, **kwargs)
        else:
            snapshot = self.get_image(snapshot_id)

        #Step 2: Create local path for copying image
        tenant = find(self.keystone.tenants, id=server.tenant_id)
        local_user_dir = os.path.join(download_dir, tenant.name)
        if not os.path.exists(local_user_dir):
            os.makedirs(local_user_dir)

        #Step 3: Download local copy of snapshot
        local_image = os.path.join(local_user_dir, '%s.qcow2' % image_name)
        logger.debug("Snapshot downloading to %s" % local_image)
        with open(local_image,'w') as f:
            for chunk in snapshot.data():
                f.write(chunk)

        logger.debug("Snapshot downloaded to %s" % local_image)
        return (local_user_dir, local_image, snapshot)

    def download_image(self, download_dir, image_id, extension=None):
        image = self.glance.images.get(image_id)
        local_image = os.path.join(download_dir, '%s' % (image_id,))
        with open(local_image,'w') as f:
            for chunk in image.data():
                f.write(chunk)
        if not extension:
            extension = self._read_file_type(local_image)
        os.rename(local_image, "%s.%s" % (local_image, extension))
        return local_image

    def upload_local_image(self, download_loc, name,
                     container_format='ovf',
                     disk_format='raw',
                     is_public=True, properties={}):
        """
        Upload a single file as a glance image
        Defaults ovf/raw are correct for a eucalyptus .img file
        """
        new_meta = self.glance.images.create(name=name,
                                             container_format=container_format,
                                             disk_format=disk_format,
                                             is_public=is_public,
                                             properties=properties,
                                             data=open(download_loc))
        return new_meta

    def upload_full_image(self, name, image_file, kernel_file, ramdisk_file):
        """
        Upload a full image to glance..
            name - Name of image when uploaded to OpenStack
            image_file - Path containing the image file
            kernel_file - Path containing the kernel file
            ramdisk_file - Path containing the ramdisk file
        Requires 3 separate filepaths to uploads the Ramdisk, Kernel, and Image
        This is useful for migrating from Eucalyptus/AWS --> Openstack
        """
        opts = {}
        new_kernel = self.upload_local_image(kernel_file,
                                       'eki-%s' % name,
                                       'aki', 'aki', True)
        opts['kernel_id'] = new_kernel.id
        new_ramdisk = self.upload_local_image(ramdisk_file,
                                        'eri-%s' % name,
                                        'ari', 'ari', True)
        opts['ramdisk_id'] = new_ramdisk.id
        new_image = self.upload_local_image(image, name, 'ami', 'ami', True, opts)
        return new_image

    def delete_images(self, image_id=None, image_name=None):
        if not image_id and not image_name:
            raise Exception("delete_image expects image_name or image_id as keyword"
            " argument")

        if image_name:
            images = [img for img in self.list_images()
                      if image_name in img.name]
        else:
            images = [self.glance.images.get(image_id)]

        if len(images) == 0:
            return False
        for image in images:
            self.glance.images.delete(image)

        return True

    # Public methods that are OPENSTACK specific

    def create_snapshot(self, instance_id, name, **kwargs):
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

        #Step 2: Wait (Exponentially) until status moves from:
        # queued --> saving --> active
        attempts = 0
        while True:
            snapshot = self.get_image(snapshot_id)
            if attempts >= 40:
                break
            if snapshot.status == 'active':
                break
            attempts += 1
            logger.debug("Snapshot %s in non-active state %s" % (snapshot_id, snapshot.status))
            logger.debug("Attempt:%s, wait 1 minute" % attempts)
            time.sleep(60)
        if snapshot.status != 'active':
            raise Exception("Create_snapshot timeout. Operation exceeded 40m")
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
        creds['key'] = kwargs.get('key')
        creds['secret'] = kwargs.get('secret')
        creds['ex_tenant_name'] = kwargs.get('ex_tenant_name')
        creds['ex_project_name'] = kwargs.get('ex_project_name')
        return creds

    def _admin_driver_creds(self, **kwargs):
        creds = {}
        creds['region_name'] = kwargs.get('region_name')
        creds['router_name'] = kwargs.get('router_name')
        creds['admin_url'] = kwargs.get('admin_url')
        creds['ex_force_auth_url'] = kwargs.get('auth_url')
        return creds

    def _build_admin_driver(self, **kwargs):
        #Set Meta
        OSProvider.set_meta()
        #TODO: Set location from kwargs
        provider = OSProvider(identifier=kwargs.get('location'))
        admin_creds = self._admin_identity_creds(**kwargs)
        logger.info("ADMINID Creds:%s" % admin_creds)
        identity = OSIdentity(provider, **admin_creds)
        driver_creds = self._admin_driver_creds(**kwargs)
        logger.info("ADMINDriver Creds:%s" % driver_creds)
        admin_driver = OSDriver(provider, identity, **driver_creds)
        return admin_driver

    def _new_connection(self, *args, **kwargs):
        """
        Can be used to establish a new connection for all clients
        """
        keystone = _connect_to_keystone(*args, **kwargs)
        nova = _connect_to_nova(*args, **kwargs)
        glance = _connect_to_glance(keystone, *args, **kwargs)
        return (keystone, nova, glance)

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

    def list_images(self):
        return self.nova.images.list()

    def get_image_by_name(self, name):
        for img in self.glance.images.list():
            if img.name == name:
                return img
        return None

    #Image sharing
    def shared_images_for(self, tenant_name=None, image_name=None):
        """

        @param can_share
        @type Str
        If True, allow that tenant to share image with others
        """
        if tenant_name:
            tenant = self.find_tenant(tenant_name)
            return self.glance.image_members.list(member=tenant)
        if image_name:
            image = self.find_image(image_name)
            return self.glance.image_members.list(image=image)

    def share_image(self, image, tenant_id, can_share=False):
        """

        @param can_share
        @type Str
        If True, allow that tenant to share image with others
        """
        return self.glance.image_members.create(
                    image, tenant_id, can_share=can_share)

    def unshare_image(self, image, tenant_id):
        tenant = find(self.keystone.tenants, name=tenant_name)
        return self.glance.image_members.delete(image.id, tenant.id)

    #Alternative image uploading

    #Lists
    def admin_list_images(self):
        """
        These images have an update() function
        to update attributes like public/private, min_disk, min_ram

        NOTE: glance.images.list() returns a generator, we return lists
        """
        return [i for i in self.glance.images.list()]

    def list_images(self):
        return [img for img in self.glance.images.list()]

    #Finds
    def get_image(self, image_id):
        found_images = [i for i in self.glance.images.list() if
                i.id == image_id]
        if not found_images:
            return None
        return found_images[0]

    def find_image(self, image_name, contains=False):
        return [i for i in self.glance.images.list() if
                i.name == image_name or
                (contains and image_name in i.name)]

    def find_tenant(self, tenant_name):
        try:
            tenant = find(self.keystone.tenants, name=tenant_name)
            return tenant
        except NotFound:
            return None
