#!/usr/bin/python

import argparse
import commands
import glob
import os
import os.path
import shutil
import subprocess
import sys
import time
import uuid

skip_dup = True
if len(sys.argv) > 1 and sys.argv[1] == 'continue':
  skip_dup = False

waggle_image_directory = os.path.dirname(os.path.abspath(__file__))
print("### Run directory for build_image.py: %s" % waggle_image_directory)
sys.path.insert(0, '%s/lib/python/' % waggle_image_directory)
from waggle.build import *

# To copy a new public image to the download webpage, copy the waggle-id_rsa ssh key to /root/.
# To generate a functional AoT image with private configuration, put id_rsa_waggle_aot_config and a clone of git@github.com:waggle-sensor/private_config.git in /root

# One of the most significant modifications that this script does is setting static IPs. Nodecontroller and guest node have different static IPs.


print "usage: python -u ./build_image.py 2>&1 | tee build.log"

start_time = time.time()

debug=0 # skip chroot environment if 1

build_uuid = uuid.uuid1()

data_directory="/root"

uuid_file = '%s/build_uuid' % data_directory
with open(uuid_file, 'w') as uuid:
  uuid.write(str(build_uuid))

report_file="/root/report.txt"

waggle_stock_url='http://www.mcs.anl.gov/research/projects/waggle/downloads/waggle_images/base/'
base_images=   {
                'odroid-xu3' : {
                        #'filename': "waggle-base-extension_node-odroid-xu4-20161005.img",
                        'filename': "ubuntu-16.04-minimal-odroid-xu3-20160706.img",
                         'url': waggle_stock_url
                        },
                'odroid-c1' : {
                        #'filename':"waggle-base-nodecontroller-odroid-c1-20161005.img",
                        'filename':"ubuntu-16.04-minimal-odroid-c1-20160817.img",
                        'url': waggle_stock_url
                    }
                }


create_b_image = 0 # will be 1 for XU4

change_partition_uuid_script = waggle_image_directory + '/change_partition_uuid.sh'   #'/usr/lib/waggle/waggle_image/change_partition_uuid.sh'

if create_b_image and not os.path.isfile(change_partition_uuid_script):
    print(change_partition_uuid_script, " not found")
    sys.exit(1)

mount_point="/mnt/newimage"

odroid_model = detect_odroid_model()

if not odroid_model:
    sys.exit(1)


is_extension_node = 0 # will be set automatically to 1 if an odroid-xu3 is detected !
if odroid_model == "odroid-xu3":
    is_extension_node = 1
    create_b_image = 1

if is_extension_node:
    image_type = "extension_node"
else:
    image_type = "nodecontroller"

# install parted
if subprocess.call('hash partprobe > /dev/null 2>&1', shell=True):
    run_command('apt-get install -y parted')

# install pipeviewer
if subprocess.call('hash pv > /dev/null 2>&1', shell=True):
    run_command('apt-get install -y pv')


print "image_type: ", image_type

date_today=get_output('date +"%Y%m%d"').rstrip()
new_image_base="waggle-%s-%s-%s" % (image_type, odroid_model, date_today)
new_image_prefix="%s/%s" % (data_directory, new_image_base)
new_image="%s.img" % (new_image_prefix)
new_image_xz = new_image+'.xz'

os.chdir(data_directory)

try:
    base_image = base_images[odroid_model]['filename']
except:
    print "image %s not found" % (odroid_model)
    sys.exit(1)

base_image_xz = base_image + '.xz'


# clean up first
unmount_mountpoint(mount_point)
time.sleep(3)
detach_loop_devices()
create_loop_devices()


###### TIMING ######
init_setup_time = time.time()
print("Initial Setup Duration: %ds" % (init_setup_time - start_time))
####################

if not os.path.isfile(base_image_xz):
    run_command('wget '+ base_images[odroid_model]['url'] + base_image_xz)

###### TIMING ######
image_fetch_time = time.time()
print("Base Image Fetch Duration: %ds" % (image_fetch_time - init_setup_time))
####################

if skip_dup or (not skip_dup and not os.path.exists(new_image_xz)):
  try:
    os.remove(new_image_xz)
  except:
    pass

  print("Copying file %s to %s ..." % (base_image_xz, new_image_xz))
  shutil.copyfile(base_image_xz, new_image_xz)

###### TIMING ######
image_copy_time = time.time()
print("Base Image Copy Duration: %ds" % (image_copy_time - image_fetch_time))
####################

if skip_dup or (not skip_dup and not os.path.exists(new_image)):
  try:
      os.remove(new_image)
  except:
      pass

  print("Uncompressing file %s ..." % new_image_xz)
  run_command('unxz --keep ' + new_image_xz)

###### TIMING ######
image_unpack_time = time.time()
print("New Image Unpacking Duration: %ds" % (image_unpack_time - image_copy_time))
####################

#
# LOOP DEVICES HERE
#

attach_loop_devices(new_image, 0, None)

time.sleep(3)
print "first filesystem check on /dev/loop0p2"
check_partition(0)



print "execute: mkdir -p "+mount_point
try:
    os.mkdir(mount_point)
except:
    pass


mount_mountpoint(0, mount_point)

###### TIMING ######
loop_mount_time = time.time()
print("Loop Mount Duration: %ds" % (loop_mount_time - image_copy_time))
####################

shutil.copyfile(uuid_file, mount_point+uuid_file)

### Copy the image build script ###
build_script = '%s/root/configure_waggle.sh' % mount_point
shutil.copyfile('%s/scripts/configure_waggle.sh' % waggle_image_directory, build_script)
os.chmod(build_script, 0733)

try:
    os.mkdir('%s/usr/lib/waggle' % mount_point)
except:
  print("ERROR: could not create /usr/lib/waggle under %s" % mount_point)
  sys.exit(2)

configure_aot = False
if os.path.exists('/root/id_rsa_waggle_aot_config') and run_command('ssh -T git@github.com', die=False) == 1:
  configure_aot = True
  print "################### AoT Configuration Enabled ###################"


if configure_aot:
  try:
    # clone the private_config repository
    run_command('git clone git@github.com:waggle-sensor/private_config.git', die=False)

    # allow the node setup script to change the root password to the AoT password
    shutil.copyfile('/root/id_rsa_waggle_aot_config', '%s/root/id_rsa_waggle_aot_config' % mount_point)
    #shutil.copyfile('/root/private_config/encrypted_waggle_password', '%s/root/encrypted_waggle_password' % mount_point)
    shutil.copyfile('/root/private_config/root_shadow', '%s/root/root_shadow' % mount_point)
    os.chmod('%s/root/root_shadow' % mount_point, 0700)

    if not is_extension_node:
      # allow the node the register in the field
      shutil.copyfile('/root/private_config/id_rsa_waggle_aot_registration', '%s/root/id_rsa_waggle_aot_registration' % (mount_point))
      os.chmod('%s/root/id_rsa_waggle_aot_registration' % mount_point, 0600)
  except Exception as e:
    print("Error in private AoT configuration: %s" % str(e))
    pass


### Pull the appropriate Waggle repositories

os.chdir('%s/usr/lib/waggle' % mount_point)
run_command('git clone --recursive https://github.com/waggle-sensor/core.git', die=True)
run_command('git clone --recursive https://github.com/waggle-sensor/plugin_manager.git', die=True)
if is_extension_node:
  run_command('git clone --recursive https://github.com/waggle-sensor/guestnode.git', die=True)
else:
  run_command('git clone --recursive https://github.com/waggle-sensor/nodecontroller.git', die=True)
os.chdir(data_directory)

# chroot can cause issues with DNS, so use the parent systems' resolv.conf
shutil.copyfile('/etc/resolv.conf', '%s/etc/resolv.conf' % mount_point)


###### TIMING ######
pre_chroot_time = time.time()
print("Additional Pre-chroot Setup Duration: %ds" % (pre_chroot_time - loop_mount_time))
####################

#
# CHROOT HERE
#

print "################### start of chroot ###################"

if debug == 0:
    run_command('chroot %s/ /bin/bash /root/configure_waggle.sh' % (mount_point))


print "################### end of chroot ###################"


###### TIMING ######
chroot_setup_time = time.time()
print("Chroot Node Setup Duration: %ds" % (chroot_setup_time - pre_chroot_time))
####################

#
# After changeroot
#

if configure_aot:
  try:
      os.makedirs('%s/usr/lib/waggle/SSL/guest' % mount_point)
  except:
    print("ERROR: could not create /usr/lib/waggle/SSL/guest under %s" % mount_point)
    sys.exit(2)
  try:
    shutil.copyfile('/root/private_config/id_rsa_waggle_aot_guest_node',
                    '%s/usr/lib/waggle/SSL/guest/id_rsa_waggle_aot_guest_node' % mount_point)

    if not is_extension_node:
      # install a copy of wvdial.conf with the AoT secret APN
      shutil.copyfile('/root/private_config/wvdial.conf', '%s/etc/wvdial.conf' % (mount_point))

    # remove temporary password setup files from image
    os.remove('%s/root/id_rsa_waggle_aot_config' % (mount_point))
    #os.remove('%s/root/encrypted_waggle_password' % (mount_point))
    os.remove('%s/root/root_shadow' % (mount_point))

    # remove the private_config repository
    shutil.rmtree('/root/private_config')
  except Exception as e:
    print("Error in private AoT configuration: %s" % str(e))
    pass
else:
  if not is_extension_node:
    # copy the default, unconfigured wvdial.conf file
    shutil.copyfile('%s/usr/lib/waggle/nodecontroller/device_rules/wwan_modems/wvdial.conf' % mount_point, '%s/etc/wvdial.conf' % mount_point)


try:
    os.remove(new_image+'.report.txt')
except:
    pass

print "copy: ", mount_point+'/'+report_file, new_image+'.report.txt'

if os.path.exists(mount_point+'/'+report_file):
    shutil.copyfile(mount_point+'/'+report_file, new_image+'.report.txt')
else:
    print "file not found:", mount_point+'/'+report_file


unmount_mountpoint(mount_point)
print "filesystem check on /dev/loop0p2 after chroot"
check_partition(0)
detach_loop_devices()

time.sleep(3)


###### TIMING ######
post_chroot_time = time.time()
print("Additional Post-chroot Setup Duration: %ds" % (post_chroot_time - chroot_setup_time))
####################

try:
  os.remove(new_image_xz)
except:
  pass

# compress A image
run_command('xz -1 '+new_image)

#
# Upload files to waggle download directory
#
if not configure_aot and os.path.isfile( data_directory+ '/waggle-id_rsa'):
    remote_path = '/mcs/www.mcs.anl.gov/research/projects/waggle/downloads/waggle_images/{0}/{1}/'.format(image_type, odroid_model)
    scp_target = 'waggle@terra.mcs.anl.gov:' + remote_path
    run_command('md5sum $(basename {0}.xz) > {0}.xz.md5sum'.format(new_image) )


    cmd = 'scp -o "StrictHostKeyChecking no" -v -i {0}/waggle-id_rsa {1}.xz {1}.xz.md5sum {2}'.format(data_directory, new_image, scp_target)

    count = 0
    while 1:
        count +=1
        if (count >= 10):
            print "error: scp failed after 10 trys\n"
            sys.exit(1)

        cmd_return = 1
        print "execute: ", cmd
        try:
            child = subprocess.Popen(['/bin/bash', '-c', cmd])
            child.wait()
            cmd_return = child.returncode

        except Exception as e:
            print "Error: %s" % (str(e))
            cmd_return = 1

        if cmd_return == 0:
            break

        time.sleep(10)


    run_command('echo "{0}" > {1}/latest.txt'.format(new_image_base +".img.xz", data_directory))
    run_command('scp -o "StrictHostKeyChecking no" -i {0}/waggle-id_rsa {0}/latest.txt {1}/'.format(data_directory, scp_target))


    if os.path.isfile( new_image+'.report.txt'):
        run_command('scp -o "StrictHostKeyChecking no" -v -i {0}/waggle-id_rsa {1}.report.txt {2}'.format(data_directory, new_image,scp_target))


    if os.path.isfile( new_image+'.build_log.txt'):
        run_command('scp -o "StrictHostKeyChecking no" -v -i {0}/waggle-id_rsa {1}.build_log.txt {2}'.format(data_directory, new_image,scp_target))

###### TIMING ######
upload_time = time.time()
print("Image Upload Duration: %ds" % (upload_time - post_chroot_time))
####################

###### TIMING ######
end_time = time.time()
print("Build Duration: %ds" % (end_time - start_time))
####################
