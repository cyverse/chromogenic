Chromogenic
====

A unified interface for imaging to/from multiple cloud providers.

Chromogenic Features:
=====================

Imaging:
- [X] Create snapshots from instance on Openstack
- [X] Create images from instance on Openstack
- [X] Create images from instance on Eucalyptus

Export:
- [~] Export cloud instance/image to double-click-to-start .ova (Virtualbox Appliance)
- [~] Export cloud instance/image to stand-alone bootable image
- [X] Export cloud instance/image to boot hard drive on VMWare (VMDK)
- [X] Export cloud instance/image to RAW or QCOW2

Migration:
- [X] Migrate image from Eucalyptus to Openstack
- [X] Migrate image between Openstack Providers
- [X] Migrate image between Eucalyptus Providers
- [ ] Migrate image from AWS to Openstack
- [ ] Migrate image from AWS to Eucalyptus

Cleaning:
- [X] Remove specific data created by deployment in ['Atmosphere'](https://github.com/iPlantCollaborativeOpenSource/atmosphere)
- [X] Remove users home directories and non-essential files
- [X] Empty logs without changing permissions or removing files

- [X] - Feature complete
- [~] - Feature in progress
- [ ] - Unsupported feature addressed in future releases

Why use chromogenic?
====================

Cloud computing is 'the next big thing' for IT. Whether you use private clouds on your own servers (Eucalyptus, Openstack) or your running instances on AWS, the idea is the same.
You click one button, wait a few minutes ( or less!) and voila, a computer is ready and waiting. Did you just 'rm -rf /' on your instance? No problem, just shut it down and startup a new instance and try it all over again.

Another great benefit to cloud computing is snapshots/imaging, which allows you to save your instance in it's current state and make it available as a new image that you can launch. However, imaging on any cloud provider can be a multi-step, intensive process.

Chromogenic takes all of the complexity out and allows you to run a single command that will do all the heavy lifting behind the scenes.

Creating An Image:
==================

```python
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

```

Here is whats happening behind the scenes:

What Happens When an Image is Created?:
======================================

* Image is cleaned (see service/imaging/clean.py)
  * User data is removed
  * Atmosphere specific data is removed
  * Log files, history files, and one-time-use files are removed
  * NOTE: These are a lot of system calls, most calls are inline-sed replacements, as well as other system level calls ( truncate -s0 \<File\> , rm \<File\> )
* Additional support available for converting from Xen -> KVM:
  * Image is converted from a 'xen-based' image to a 'kvm-based' image
  * Xen specific modules are removed, KVM specific modules are added in their place
  * The ramdisk includes the required virtio modules to make the image boot on OStack.


ASSUMPTIONS:
================
* All commands should be run as root (Because of chroot and mount commands)
* You should have at least TWICE (2x) as much free space as the size of the image you are going to create, due to the process of Tarring, compressing, and parting the files.

* Some commands must be run 'within a  chroot jail' (see [chroot](http://en.wikipedia.org/wiki/Chroot) for more information), this is what chroot jail looks like:
```bash
  mount -t proc /proc /mnt/proc/
  mount -t sysfs /sys /mnt/sys/
  mount -o bind /dev /mnt/dev/
  <chroot.. Commands run (Installing packages, rebuilding the ramdisk).. Exit>
  umount /mnt/proc/
  umount /mnt/sys/
  umount /mnt/dev/
```

# How to Install
```bash
pip install git+git://github.com/iPlantCollaborativeOpenSource/chromogenic#egg=chromogenic
```

# License

Apache Software License

