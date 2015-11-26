#!/usr/bin/env python2

### This program is free software; you can redistribute it and/or
### modify it under the terms of the GNU General Public License
### as published by the Free Software Foundation; either version 2
### of the License, or (at your option) any later version.
###
### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.
###
### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

### Copyright 2015-2016 Dag Wieers <dag@wieers.com>
import sys
import os
import optparse
import cPickle as pickle
import time

VERSION = '0.1'

#parser = optparse.OptionParser(version='%prog %s' % VERSION)
#parser

### TODO: Check how df identifies 'normal' file systems
### TODO: Maybe use and include-list instead, or allow both ?
excluded_fstypes = (
    'autofs',
    'binfmt_misc',
    'devpts',
    'devtmpfs',
    'nfs',
    'nfs4',
    'nfsd',
    'proc',
    'rpc_pipefs',
    'selinuxfs',
    'sysfs',
    'tmpfs',
)

database = 'remapid-%s.idx' % time.strftime('%Y%m%d-%H%M', time.localtime())
debug = True
info = True
parent = '.'

store = {
  'uid': { },
  'gid': { },
}

### TODO: Example mapping for testing on /dev and /tmp (to be stored in an external file)
uidmap = {
  10: 10010,   # uucp
  42: 10042,   # gdm
  48: 10048,   # apache
  69: 10069,   # vcsa
}

gidmap = {
  5: 10005,    # tty
  16: 100016,  # oprofile
  39: 10039,   # video
  42: 10042,   # gdm
  69: 10069,   # vcsa
  484: 10484,  # tmux
  505: 10505,  # vboxusers
}

if len(sys.argv) > 1:
    parent = sys.argv[1]

def find_excluded_devices():
    ''' Return a list of file system devices that are excluded '''
    excluded_devices = []
    for l in open('/proc/mounts', 'r'):
        (dev, mp, fstype, opts, x, y) = l.split()
        if fstype in excluded_fstypes:
            excluded_devices.append(os.lstat(mp).st_dev)
    return excluded_devices

### Make a list of excluded (mount) devices:
excluded_devices = find_excluded_devices()

for root, dirs, files in os.walk(parent, topdown=False):

    ### For speed, drop every root that is on an excluded device
    if os.lstat(root).st_dev in excluded_devices:
        continue

    ### Find paths that require remapping and store them
    for path in dirs + files:
        ### Make path absolute
        path = os.path.join(root, path)

        try:
            s = os.lstat(path)
#            print path, s.st_uid, s.st_gid
        except OSError, e:
            print >>sys.stderr, 'WARNING: %s' % e

        if s.st_uid in uidmap.keys():
            if debug:
                print >>sys.stderr, 'DEBUG: Found path %s owned by uid %d' % (path, s.st_uid)
            if s.st_uid not in store['uid'].keys():
                store['uid'][s.st_uid] = [ path ]
            else:
                store['uid'][s.st_uid].append(path)

        if s.st_gid in gidmap.keys():
            if debug:
                print >>sys.stderr, 'DEBUG: Found path %s owned by gid %d' % (path, s.st_gid)
            if s.st_gid not in store['gid'].keys():
                store['gid'][s.st_gid] = [ path ]
            else:
                store['gid'][s.st_gid].append(path)

print store

### FIXME: Handle the case where the file already exists using tempfile
### Dump database
try:
    pickle.dump(store, open(database, 'wb'))
except:
    print >>sys.stderr, 'ERROR: Unable to dump database %s !' % database
    raise