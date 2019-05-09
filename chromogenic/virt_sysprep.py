commands = r"""touch /etc/group
edit /etc/group:s/^users:x:100:.*/users:x:100:/
edit /etc/group:s/^.+:x:1[0-9][0-9][0-9]:\n//

touch /etc/ssh/sshd_config
edit /etc/ssh/sshd_config:s/^AllowGroups users root.*\n//

touch /etc/rc.local
edit /etc/rc.local:s/.*vncserver$//

touch /etc/fstab
edit /etc/fstab:s/\/dev\/sda[2-9].*\n//
edit /etc/fstab:s/\/dev\/sda1[0-9].*\n//
edit /etc/fstab:s/\/dev\/vd[b-z].*\n//

%s
# Cloud config
mkdir /etc/cloud
touch /etc/cloud/cloud.cfg
edit /etc/cloud/cloud.cfg:s/^users:/#users:/
edit /etc/cloud/cloud.cfg:s/^[ ]* - default/#  - default/
edit /etc/cloud/cloud.cfg:s/^disable_root: true/disable_root: false/
edit /etc/cloud/cloud.cfg:s/^disable_root: 1/disable_root: 0/
edit /etc/cloud/cloud.cfg:s/^ssh_deletekeys:.*1/ssh_deletekeys: 0/
edit /etc/cloud/cloud.cfg:s/^ssh_deletekeys:.*true/ssh_deletekeys: false/

# Multi-line deletes
edit /etc/sudoers:BEGIN{undef $/;} s/\n\#\# Atmosphere System.*\#\# End Atmosphere System\n//smg
edit /etc/sudoers:BEGIN{undef $/;} s/\n\# Begin Nagios.*\# End Nagios\n//smg
edit /etc/sudoers:BEGIN{undef $/;} s/\n\# Begin Sensu.*\# End Sensu\n//smg
edit /etc/sudoers:BEGIN{undef $/;} s/\n\#includedir \/etc\/sudoers\.d.*\n/\#includedir \/etc\/sudoers\.d\n/smg

edit /etc/ssh/sshd_config:BEGIN{undef $/;} s/\#\# Atmosphere System.*\#\# End Atmosphere System\n//smg
edit /etc/skel/.bashrc:BEGIN{undef $/;} s/\#\# Atmosphere System.*\#\# End Atmosphere System\n//smg

# CyVerse/Atmo stuff
delete /var/log/atmo
touch /etc/rc.local.atmo
delete /etc/rc.local.atmo
delete /opt/cyverse
touch /usr/sbin/atmo_boot.py
delete /usr/sbin/atmo_boot.py

# Delete some directory contents
mkdir /mnt
delete /mnt
mkdir /mnt
delete /tmp
mkdir /tmp
delete /proc
mkdir /proc

# Log files
truncate-recursive /var/log
touch /etc/udev/rules.d/70-persistent-net.rules
truncate /etc/udev/rules.d/70-persistent-net.rules
touch /lib/udev/rules.d/75-persistent-net-generator.rules
truncate /lib/udev/rules.d/75-persistent-net-generator.rules

root-password password:atmosphere
%s
"""

ubuntu = ""

centos = """# Sysconfig stuff
mkdir /etc/sysconfig
mkdir /etc/sysconfig/network-scripts
touch /etc/sysconfig/network-scripts/ifcfg-eth0
edit /etc/sysconfig/network-scripts/ifcfg-eth0:s/^HWADDR=*\\n//
edit /etc/sysconfig/network-scripts/ifcfg-eth0:s/^MACADDR=*\\n//

# SELinux stuff
mkdir /etc/syslinux
touch /etc/syslinux/selinux
edit /etc/syslinux/selinux:s/SELINUX=.*/SELINUX=disabled/
mkdir /etc/selinux
touch /etc/selinux/config
edit /etc/selinux/config:s/SELINUX=.*/SELINUX=disabled/
"""
