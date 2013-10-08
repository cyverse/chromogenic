These are the steps necessary to build bootable vms

STEP 0: Make a local copy of the instance
===================================
The first step is to copy all the data from your instance into a raw image. 


There are two ways of doing this:

1. From within the VM: (AWS)
    Usually it is best to use an EBS volume for this method, otherwise ensure you have sufficient storage to hold a copy of the entire file-system of the instance:
```bash
        dd if=/dev/sda1 of=/mounted_vol/copy_of_instance.img
```
2. From the Node Controller: (Eucalyptus/Openstack)
    This method is only applicable when you have a private cloud AND have access to the node controller, but it is the fastest and most efficient way of copying the data.
    The euca_conf command and the location of the instance's root disk are specific to eucalyptus. However every private cloud should have its own set of tools/API calls to determine which node your instance is on:
```bash
        ssh <username>@<node_controller_ip>
        #Find out which node the instance exists on
        euca_conf --list-nodes | grep <instance_id>
        scp <username>@<node_containing_instance_id>:/usr/local/eucalyptus/<username>/<instance_id>/root copy_of_instance.img
```

STEP 1: Migrating from XEN to KVM (Skip if using KVM/Openstack)
=============================================
Now we have a copy of the instance in a raw file. However, eucalyptus (and AWS) use XEN to manage instances, while VirtualBox supports KVM.

Here are a few very important files and the changes I had to make to transition to KVM. While every option may not apply in your case, these files are very important, so look through them and make sure the values are correct!

1. /etc/inittab:

    Original: id:3:initdefault

    Change: id:5:initdefault

    Reason: Boot the user in X11 instead of CLI

    ...
    Original: xvc0:2345:respawn:/sbin/mingetty xvc0

    Change: <Remove the line>

    Reason: xvc0 did not exist on virtualbox, presumably this is specific to being run withing the XEN environment.

ORIGINAL (XEN) SAMPLE:
    # inittab       This file describes how the INIT process should set up
    #               the system in a certain run-level.
    #
    # Author:       Miquel van Smoorenburg, <miquels@drinkel.nl.mugnet.org>
    #               Modified for RHS Linux by Marc Ewing and Donnie Barnes
    #
    # Default runlevel. The runlevels used by RHS are:
    #   0 - halt (Do NOT set initdefault to this)
    #   1 - Single user mode
    #   2 - Multiuser, without NFS (The same as 3, if you do not have networking)
    #   3 - Full multiuser mode
    #   4 - unused
    #   5 - X11
    #   6 - reboot (Do NOT set initdefault to this)
    # 
    id:3:initdefault:
    
    # System initialization.
    si::sysinit:/etc/rc.d/rc.sysinit
    
    l0:0:wait:/etc/rc.d/rc 0
    l1:1:wait:/etc/rc.d/rc 1
    l2:2:wait:/etc/rc.d/rc 2
    l3:3:wait:/etc/rc.d/rc 3
    l4:4:wait:/etc/rc.d/rc 4
    l5:5:wait:/etc/rc.d/rc 5
    l6:6:wait:/etc/rc.d/rc 6
    
    # Trap CTRL-ALT-DELETE
    ca::ctrlaltdel:/sbin/shutdown -t3 -r now
    
    # When our UPS tells us power has failed, assume we have a few minutes
    # of power left.  Schedule a shutdown for 2 minutes from now.
    # This does, of course, assume you have powerd installed and your
    # UPS connected and working correctly.  
    pf::powerfail:/sbin/shutdown -f -h +2 "Power Failure; System Shutting Down"
    
    # If power was restored before the shutdown kicked in, cancel it.
    pr:12345:powerokwait:/sbin/shutdown -c "Power Restored; Shutdown Cancelled"
    
    
    # Run gettys in standard runlevels
    1:2345:respawn:/sbin/mingetty tty1
    2:2345:respawn:/sbin/mingetty tty2
    3:2345:respawn:/sbin/mingetty tty3
    4:2345:respawn:/sbin/mingetty tty4
    5:2345:respawn:/sbin/mingetty tty5
    6:2345:respawn:/sbin/mingetty tty6
    
    # Run xdm in runlevel 5
    x:5:respawn:/etc/X11/prefdm -nodaemon
    xvc0:2345:respawn:/sbin/mingetty xvc0

2. /etc/modprobe.conf:

    The modprobe.conf file contains a list of additional modules that are necessary when building a new ramdisk, and will probably contain xen specific modules that should be replaced.
    
    The lines in the replacement/kvm sample were selected by CentOS when installing the OS on a blank hard drive. These modules may be different on OS that aren't CentOS 5

ORIGINAL (XEN) SAMPLE:

    alias scsi_hostadapter xenblk
    alias eth0 xennet

REPLACEMENT (KVM) SAMPLE:

    # Necessary for KVM/OpenStack
    alias eth0 e1000 
    # All these below are for VirtualBox (SoundCard)
    alias scsi_hostadapter ata_piix
    alias scsi_hostadapter1 ahci
    install pciehp /sbin/modprobe -q --ignore-install acpiphp; /bin/true
    alias snd-card-0 snd-intel8x0
    options snd-card-0 index=0
    options snd-intel8x0 index=0
    remove snd-intel8x0 { /usr/sbin/alsactl store 0 >/dev/null 2>&1 || : ; }; /sbin/modprobe -r --ignore-remove snd-intel8x0

3. /etc/fstab
    
    NOTE: Ensure that root (/) is set to sda:

    ...

    /dev/sda1         /             ext3     defaults,errors=remount-ro 0 0

    ...

4. CHROOT FUN!
    Run these commands within a chroot environment! /dev, /proc, and /sys should be mounted in addition to the image! (See BEFORE WE BEGIN)

    3a. Set a new root password
        A random root password is set when booting from the cloud, so change it to something you will remember!

        passwd root
    
    3b. Yum install 
        Anyone who wants their VM locally will need these essentials (Grub bootloader, Kernel+Ramdisk, GUI)
    
        yum groupinstall -y "X Window System" "GNOME Desktop Environment"
        yum install -y kernel mkinitrd grub
        #If the ramdisk_name is <initrd-2.6.18-348.3.1.el5.img> the kernel_version is <2.6.18-348.3.1.el5>
        mkinitrd --with virtio_pci --with virtio_ring --with virtio_blk --with virtio_net --with virtio_balloon --with virtio -f /boot/<ramdisk_name> <kernel_version>
        
    
        Sidenotes:
        * selinux is part of the groupinstall for 'X Window System', I set the policy from 'enforcing' to 'disabled' until the VM has been launched successfully, failure to do so will result in selinux killing the VM during the boot sequence.
        * My company also required that I remove realvnc-vnc-server and openldap before exporting the image, if you choose to do this you should remove these packages BEFORE the 'yum groupinstall' command, or many of the packages will be removed as dependencies.
        * The --with virtio* stuff was necessary when converting Image/Instances (from Eucalyptus --> Openstack) , so I left it in, but it may not be used by VirtualBox.
    
5. /boot/grub/grub.conf 

    Now that we know grub is installed, we need to update our grub.conf
    Grub is not used to boot VMs in a cloud environment, so you may or may not already have a grub.conf. 
    Here is what a sample grub.conf should look like (Note that root=/dev/sda1, and that ramdisk_name and kernel_version should be replaced appropriately):

    default=0
    timeout=3
    splashimage=(hd0,0)/boot/grub/splash.xpm.gz
    title CentOS (<kernel_version>)
        root (hd0,0)
        kernel /boot/vmlinuz-<kernel_version> root=/dev/sda1 ro enforcing=0
        initrd /boot/<ramdisk_name>

    TIP: To ensure full support with grub and grub-legacy, create a symlink from grub.cfg and menu.lst to grub.conf

STEP 2: Building a bootable image
=================================
We have our cloud instance and we have prepared it for a KVM environment, but this image is NOT bootable! Instead, we need to create a new raw drive and partition it to properly boot from the disk.

#1. Create a blank raw image that is larger than your current image

    qemu-img create -f raw newimage.raw 10G
    losetup -fv newimage.raw
    (Example Output: loop device is /dev/loop0)

#2. Partition the disk (on /dev/loop0) using fdisk 

    2a. For the humans: cfdisk
        The easiest and most intuitive way to partition the disk...
        
            cfdisk /dev/loop0
            #just partition the whole disk,  select bootable, then write (Don't forget to do this one), and finally quit
        
        However cfdisk is not scriptable. For that we would use...
    
    2b. For the scripts: sfdisk
    
        sfdisk -D /dev/loop0 << "EOF
        ,,L,*
        ;
        ;
        ;
        EOF"
    The input string above is actually identical to the process described in cfdisk.
     If we were to 'read' it line by line we would get:
        partition 1: (start_of_disk,end_of_disk,(L)=LinuxPartition, (*)=Bootable)
        partition 2: empty
        partition 3: empty
        partition 4: empty
    
#3. Create a filesystem

mkfs cannot be used with the default options because it screws up when calculating the filesystem size on a loopback device. To get around this we will offset to start at the first partition and calculate where the end of the disk is:

First, we look at our newly partitioned disk and take note of:
* Start (Start of Partition)
* End (End of Partition)
* Blocks (Total # of blocks)
* Cylinders
* Heads (Usually 255)
* Sectors (Usually 63)

    > fdisk -l -u /dev/loop0
    Disk /dev/loop0: 10.7 GB, 10737418240 bytes
    255 heads, 63 sectors/track, 1305 cylinders, total 20971520 sectors
    Units = sectors of 1 * 512 = 512 bytes
    Sector size (logical/physical): 512 bytes / 512 bytes
    I/O size (minimum/optimal): 512 bytes / 512 bytes
    Disk identifier: 0x00000000
    
          Device Boot      Start         End      Blocks   Id  System
    /dev/loop0p1   *          63    20964824    10482381   83  Linux

First we calculate the offset from the beginning of the disk to the first partition (To skip over our 'boot partition')
    #offset = sector_size * start_sector = 512 * 63 = 32256
    losetup -fv -o 32256 newimage.raw
    (Example Output: loop device is /dev/loop1)

Now we can create a filesystem, but we need to know the block size (The standard is 4096) and the number of blocks to use, using the fdisk stats above we calculate the total number of blocks to be:
    block_total = ((end - start) * units_in_bytes) / blocksize = ((20964824 - 63) * 512) / 4096 = 2620595
    mkfs.ext3 -b 4096 /dev/loop1 2620595
    (Lots of output..)

#4. Move image of instance on to the new hard drive.

Now we have two images, one that has a bootable partition and ~10G of empty space, and an instance that is < 10G, so now we can move all that data to the new image.

    mkdir -p /mnt/bootable_raw_here
    mkdir -p /mnt/original_raw_here
    mount -t ext3 /dev/loop1 /mnt/bootable_raw_here
    mount -t ext3 copy_of_instance.img /mnt/original_raw_here
    rsync --inplace -a /mnt/original_raw_here/* /mnt/bootable_raw_here/
    umount /mnt/original_raw_here

#5. Enable grub as the bootloader on newimage.raw

    5a. Copy stage files!

    This step gave me a major headache. First I will explain why, and then how we can get around it:

    The Problem:
        1. Eucalyptus/AWS/Openstack all run AMI's the same way.. Each cloud provider acts as the bootloader and requires the disk image, the kernel and the ramdisk it is using, and then does the booting for you.
        2. Because of that, your instance has most likely NEVER had grub on it. This is NOT a typical use case anywhere except in the world of the cloud/virtualization. I spoke with many people in #centos and #grub, and was essentially told that my only option was booting a LiveCD with my HDD and then installing grub. This would have been hell to automate so I
 was determined to find a better way.

    The Solution:
        The best way to get these stage files it to install your OS of choice on an empty hard drive using virtualbox. The CD will install grub, create device.map and fill the modprobe.conf appropriately, as an added bonus you will end up with is a 'working copy' of your OS on virtualbox that you can compare your machine to when things go wrong (And they will.
 Keep this one around).
        Once you have a bare install of your OS of choice, copy the stage1, stage2, device.map, and e2fs_stage1_5 from /boot/grub/ on the Virtualbox VM to /boot/grub/ on your new image

    5b. Install GRUB natively

    The command:
        grub --device-map=/dev/null
    Will get you to the grub CLI:
        grub> device (hd0) newimage.raw
        grub> geometry (hd0) 1305 255 63 # Cylinders, heads, sectors (from fdisk output ^^)
        grub> root (hd0,0)
        grub> setup (hd0)
        Checking if"/boot/grub/stage1" exists... yes
        Checking if"/boot/grub/stage2" exists... yes
        Checking if"/boot/grub/e2fs_stage1_5" exists... yes
        Running "embed /boot/grub/e2fs_stage1_5 (hd0)"...  17 sectors are embedded.
        succeeded
        Running "install /boot/grub/stage1 (hd0) (hd0)1+17 p (hd0,0)/boot/grub/stage2 /boot/grub/menu.lst"... succeeded
        Done.
        grub> quit

#6. Unmount and remove loop devices

    umount /mnt/bootable_raw_here
    losetup -d /dev/loop0
    losetup -d /dev/loop1

STEP 3: Going from bootable image to VirtualBox App
===================================================

Now that we have a bootable disk, all thats left is running VBoxManage a few times to wrap a container of settings around the virutal hard drive

#1. Converting from RAW to a virtual hard drive
    VBoxManage convertfromraw newimage.raw my_hdd.vdi

#2. Virtual hard drive --> OVA
    VBoxManage createvm --name "example-vmname" --ostype Linux --register
    VBoxManage modifyvm "example-vmname" --memory 512 --acpi on --ioapic on
    VBoxManage storagectl "example-vmname" --name "SATA Controller" --add sata --controller IntelAHCI
    VBoxManage storageattach "example-vmname" --storagectl "SATA Controller" --port 0 --device 0 --type hdd --medium "my_hdd.vdi"
    VBoxManage export "example-vmname" --output "example-vmname.ova"

#3. Cleanup
    By now you have all sorts of files you dont need anymore, and they are taking up A LOT of space! Go remove your .img, .vdi and bootable raw (After you have tested your OVA actually works, of course!)

Troubleshooting VirtualBox Booting:
===================================
* Don't forget to remove any cloud-specific code from /etc/rc.local, or your process may hang on boot!

* Problem:
    Grub complains when you run setup:
        Checking if"/boot/grub/stage1" exists... no <Exit>
  Solution:
    Copy stage files over (You may have to build the OS from a LiveCD/Install CD to complete this section.. I believe stage files differ between different OS's)

* Problem:
    You see this on boot, then the PC hangs:
    mount: could not find filesystem 'dev/root'
    setuproot: moving /dev failed: No such file or directory
    setuproot: eroor mounting /proc: No such file or directory
    setuproot: eroor mounting /sys: No such file or directory
    switchroot: mount failed: No such file or directory
    Kernel panic - not syncing: Attempted to kill init!
  Solution:
    create a new ramdisk with 'mkinitrd' and make sure /etc/fstab is correct
  Solution 2:
    Check your /etc/fstab, here are some 'valid' lines, yours should look like one of these:
    *   /dev/sda1         /             ext3     defaults,errors=remount-ro 0 0
    *   LABEL=root        /             ext3     defaults,errors=remount-ro 0 0  && when you check the disk (e2label <nameofimage> or file <nameofimage> the label says root

  Less likely solution: Your partition is not the first partition, so you will need to modify the /etc/fstab appropriately (This should never be the case if we follow the instructions above...)


Credit where credit is due -- Original References
========================================
http://church.cs.virginia.edu/genprog/index.php/Converting_an_EC2_AMI_to_a_VirtualBox_.vdi 
