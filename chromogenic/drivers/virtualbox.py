"""
ExportManager:

"""

import getopt
import glob
import logging
import os
import subprocess
import sys
import time

from hashlib import md5
from datetime import datetime
from urlparse import urlparse
from xml.dom import minidom

from boto import connect_ec2
from boto.ec2.regioninfo import RegionInfo
from boto.ec2.instance import Instance
from boto.s3.connection import S3Connection, OrdinaryCallingFormat
from boto.exception import S3ResponseError, S3CreateError
from boto.s3.key import Key
from boto.resultset import ResultSet

try:
    from euca2ools import Euca2ool, FileValidationError, Util, ConnectionFailed
except ImportError:
    pass


from django.utils import timezone

from chromogenic.drivers.eucalyptus import ImageManager as EucaImageManager
from chromogenic.drivers.migration import Xen2KVM
from chromogenic.drivers.base import BaseDriver
from chromogenic.boot import add_grub
from chromogenic.common import sed_delete_multi, sed_replace, sed_append
from chromogenic.common import run_command, copy_disk, create_empty_image
from chromogenic.common import mount_image, check_distro
from chromogenic.clean import remove_ldap, reset_root_password
from chromogenic.export import add_virtualbox_support

logger = logging.getLogger(__name__)

class ImageManager(BaseDriver):
    """
    Convienence class that can convert VMs into localized machines for
    Oracle Virtualbox
    """
    credentials = None
    format_type = None

    def __init__(self, format_type, *args, **kwargs):
        self.format_type = format_type
        self.credentials = kwargs


    def create_image(self, instance_id, image_name, *args, **kwargs):
        """
        """
        raise Exception("To create a virtualbox image,"
                " pass the ImageManager class and arguments as the destination"
                " fields in a migration")
    def clean_hook(self, image_path, mount_point, *args, **kwags):
        """
        Run in 'mount_and_clean' method..
        """
        remove_ldap(mount_point)
        reset_root_password(mount_point, 'atmosphere')
        #Try to make it 'bootable' container
        if self.format_type in ['ova', 'ovf']:
            add_virtualbox_support(mount_point, image_path)

    def _format_meta_name(self, name, owner, timestamp_str=None, creator='admin'):

        if not timestamp_str:
            timestamp_str = datetime.now().strftime('%m%d%Y_%H%M%S')
        #Prepare name for imaging
        name = name.replace(' ', '_').replace('/', '-')
        meta_name = '%s_%s_%s_%s' % (creator, owner, name, timestamp_str)
        return meta_name

    def parse_upload_args(self, **kwargs):
        return self.parse_export_args(**kwargs)

    def parse_export_args(self, **kwargs):
        return {
            'image_location': kwargs.get('download_location'),
            'image_name': kwargs.get('image_name'),
            'export_format': kwargs.get('format_type'),
            'keep_image': kwargs.get('keep_image',True),
            'upload': kwargs.get('upload',False),
        }


    def upload_image(self, image_location, image_name, export_format, *args, **kwargs):
        return self.export_image(image_location, image_name, export_format, **kwargs)

    def export_image(self, local_img_path, vm_name, export_format, upload=False, *args, **kwargs):
        #Convert the image if it was not passed as a kwarg
        if export_format in ['raw', 'img']:
            #We're already done.
            completed_path = local_img_path
        elif export_format in ['vmdk', 'vdi']:
            harddrive_path = self._create_virtual_harddrive(
                    local_img_path, export_format)
            logger.info("Created a local harddrive:%s" % harddrive_path)
            completed_path = harddrive_path
        elif export_format in ['ova', 'ovf']:
            raise Exception("OVA/OVF files lack a working implementation")
            harddrive_path = self._create_virtual_harddrive(
                    local_img_path, 'vmdk')
            appliance_path = self._build_new_export_vm(vm_name, harddrive_path)
            logger.info("Created VBox Appliance:%s" % appliance_path)
            completed_path = appliance_path
        if not upload:
            return (None, completed_path)

        ##Archive/Compress/Send the export to S3
        md5sum = self._large_file_hash(completed_path)
        logger.info("Hash of file complete:%s == %s"
                     % (completed_path, md5sum))
        tarfile_name = completed_path+'.tar.gz'
        self._tarzip_image(tarfile_name, [appliance_path])
        s3_keyname = 'vbox_export_%s_%s' % (instance_id,datetime.now().strftime('%Y%m%d_%H%M%S'))
        url = self._export_to_s3(s3_keyname, tarfile_name)
        return (md5sum, url)

    def _copy_to_raw(self, local_img_path, pad_size=1):
        ext="raw"
        #Image is now ready to be placed on a bootable drive, then install grub-legacy
        image_size = self._get_file_size_gb(local_img_path)
        local_raw_path = local_img_path +  "." + ext
        create_empty_image(local_raw_path, ext,
                           #TODO: Make extra size a configurable.
                           image_size+pad_size,  # Add some empty space..
                           bootable=True)
        download_dir = os.path.dirname(local_img_path)
        mount_point = os.path.join(download_dir,"mount_point/")
        #copy the data
        copy_disk(old_image=local_img_path,
                  new_image=local_raw_path,
                  download_dir=download_dir)
        #Add grub.
        #try:
        #    mount_image(local_raw_path, mount_point)
        #    add_grub(mount_point, local_raw_path)
        #finally:
        #    run_command(['umount', mount_point])
        return local_raw_path

    def _strip_uuid(self, createvm_output):
        import re
        regex = re.compile("UUID: (?P<uuid>[a-zA-Z0-9-]+)")
        r = regex.search(createvm_output)
        uuid = r.groupdict()['uuid']
        return uuid


    def _build_new_export_vm(self, name, harddrive_path, vm_opts={}, distro='Linux'):
        export_dir = os.path.dirname(harddrive_path)
        hostname_out, _ = run_command(['hostname'])
        export_file = os.path.join(export_dir,'%s_%s_%s.ova' % (name,
            hostname_out.strip(), timezone.now().strftime("%Y_%m_%d_%H_%M_%S")))
        if os.path.exists(export_file):
            #Remove vm method here..
            pass

        out, err = run_command(['VBoxManage','createvm','--basefolder',
            export_dir, '--name', name, '--ostype', distro, '--register'])
        vm_uuid = self._strip_uuid(out)
        modify_vm_opts = {
            'vram':'16',  # vram <= 8 MB causes poor performance..

            'memory':512,
            'acpi': 'on',
            'ioapic':'on'
        }
        modify_vm_opts.update(vm_opts)
        modify_vm_command = ['VBoxManage','modifyvm', vm_uuid]
        for (k,v) in modify_vm_opts.items():
            modify_vm_command.append('--%s' % k)
            modify_vm_command.append('%s' % v)
        run_command(modify_vm_command)
        run_command(['VBoxManage', 'storagectl', vm_uuid, '--name', 'Hard Drive', '--add', 'sata', '--controller', 'IntelAHCI'])
        run_command(['VBoxManage', 'storageattach', vm_uuid, '--storagectl', 'Hard Drive', '--type', 'hdd', '--medium', harddrive_path, '--port','0','--device','0'])
        run_command(['VBoxManage', 'export', vm_uuid, '--output', export_file])
        return export_file
        
        
    def _get_file_size_gb(self, filename):
        #TODO: Move to export.py
        import math
        byte_size = os.path.getsize(filename)
        one_gb = 1024**3
        gb_size = math.ceil( float(byte_size)/one_gb )
        return int(gb_size)


    #def _export_to_s3(self, keyname, the_file, bucketname='eucalyptus_exports'):
    #    key = self.euca_img_manager._upload_file_to_s3(bucketname, keyname, the_file) #Key matches on basename of file
    #    url = key.generate_url(60*60*24*7) # 7 days from now.
    #    return url

    def _large_file_hash(self, file_path):
        #TODO: Move to export.py
        logger.debug("Calculating MD5 Hash for %s" % file_path)
        md5_hash = md5()
        with open(file_path,'rb') as f:
            for chunk in iter(lambda: f.read(md5_hash.block_size * 128), b''): #b'' == Empty Byte String
                md5_hash.update(chunk)
        return md5_hash.hexdigest()

    def _tarzip_image(self, tarfile_path, file_list):
        #TODO: Move to export.py
        import tarfile
        tar = tarfile.open(tarfile_path, "w:gz")
        logger.debug("Creating tarfile:%s" % tarfile_path)
        for name in file_list:
            logger.debug("Tarring file:%s" % name)
            tar.add(name)
        tar.close()

    def _create_virtual_harddrive(self, local_img_path, disk_type):
        if 'vmdk' in disk_type:
            convert_img_path = os.path.splitext(local_img_path)[0] + '.vmdk'
            run_command(['qemu-img', 'convert', local_img_path, '-O', 'vmdk', convert_img_path])
        elif 'vdi' in disk_type:
            raw_img_path = os.path.splitext(local_img_path)[0] + '.raw'
            #Convert to raw if its anything else..
            if '.raw' not in local_img_path:
                run_command(['qemu-img', 'convert', local_img_path, '-O', 'raw', raw_img_path])
            #Convert from raw to vdi
            convert_img_path = os.path.splitext(local_img_path)[0] + '.vdi'
            #NOTE: Must DELETE first!
            run_command(['VBoxManage', 'convertdd',raw_img_path, convert_img_path])
        else:
            convert_img_path = None
            logger.warn("Failed to export. Unknown type: %s" % (disk_type,) )
        return convert_img_path
