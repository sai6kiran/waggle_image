#!/bin/bash
set -e

# This script tries to get the time from the beehive server. 

ODROID_MODEL=`head -n 1 /media/boot/boot.ini | cut -d '-' -f 1 | tr -d '\n'`
NODE_CONTROLLER_IP=`cat /etc/waggle/node_controller_host`
if [ "x$ODROID_MODEL" == "xODROIDC" ]; then
  server_hostname_file="/etc/waggle/server_host"
  while [ ! -e $server_hostname_file ]; do
    sleep 1h
  done
  SERVER_HOST=`cat $server_hostname_file`
fi


try_set_time()
{
  # check if time is needed
  #CURRENT_YEAR=$(date +"%Y")
  #if [ "${CURRENT_YEAR}x" == "x" ] ; then
  #  CURRENT_YEAR=0
  #fi
  #if [ ! ${CURRENT_YEAR} -lt ${REFERENCE_YEAR} ] ; then
  #  echo "date seems to be ok"
  #  return 0
  #fi
  #echo "Device seems to have the wrong date: year=${CURRENT_YEAR}"

  # get epoch from server
  set +e
  if [ "x$ODROID_MODEL" == "xODROIDXU" ]; then
    EPOCH=$(ssh -i /usr/lib/waggle/SSL/guest/id_rsa_waggle_aot_guest_node -o "StrictHostKeyChecking no" -o "ConnectTimeout 30" waggle@${NODE_CONTROLLER_IP} -x date +%s)
  else
    echo ${SERVER_HOST}
    EPOCH=$(curl --connect-timeout 10 --retry 100 --retry-delay 10 http://${SERVER_HOST}/api/1/epoch | grep -oP '{"epoch": \d+}' | grep -oP '\d+')
  fi
  set -e

  # if EPOCH is not empty, set date
  if [ ! "${EPOCH}x" == "x" ] ; then
    set -x
    date -s@${EPOCH}
    SUCCESS=$?
    set +x
    if [ ${SUCCESS} -eq 0 ] ; then
       return 0
    fi
    return 1
  fi
  return 1
}

########### start ###########

while [ 1 ] ; do
  
  while [ 1 ] ; do
    try_set_time
    if [ $? -eq 0 ] ; then
      break
    fi
    # did not set time, will try again.
    sleep 10
  done

  echo "sleep 24h"
  sleep 24h
done



