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
FORMAT_VERSION = 1

### FIXME: Allow the user to influence this on the commandline
### TODO: Maybe use an include-list instead, or allow both ?
excluded_fstypes = ( 'cifs', 'nfs', 'nfs4', 'sshfs', )
#included_fstypes = ( 'ext3', 'ext4', 'xfs', )

debug = True
info = True
parent = '.'

store = {
  'version': FORMAT_VERSION,
  'start': time.localtime(),
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

subcommands = ('index', 'status', 'remap', 'restore')

def debug(msg):
    if options.debug:
        print >>sys.stderr, 'DEBUG:', msg

### TODO: Allow to exclude specific filesystem types (e.g. nfs, nfs4, etc...)
def find_excluded_devices():
    ''' Return a list of file system devices that are excluded '''
    excluded_devices = []
    for l in open('/proc/mounts', 'r'):
        (dev, mp, fstype, opts, x, y) = l.split()
        s = os.statvfs(mp)
        if s.f_blocks == 0:
            debug('Exclude pseudo filesystem %s of type %s' % (mp, fstype))
            excluded_devices.append(os.lstat(mp).st_dev)
        if fstype in excluded_fstypes:
            debug('Exclude filesystem %s of type %s' % (mp, fstype))
            excluded_devices.append(os.lstat(mp).st_dev)
    return excluded_devices

parser = optparse.OptionParser(version='%prog '+VERSION)
parser.add_option( '-d', '--debug', action='store_true',
    dest='debug', help='Enable debug mode.' )
parser.add_option( '-f', '--file', action='store',
    dest='index', help='Index file to store to/read from.' )
parser.add_option( '-v', '--verbose', action='count',
    dest='verbose', help='Be more and more and more verbose.' )

group = optparse.OptionGroup(parser, "Index options",
                    "These options only apply to Index mode.")
group.add_option('-m', '--map', action='store',
    dest='map', help='Map file to use for UID/GID remapping.' )
group.add_option('-x', '--one-file-system', action='store_true',
    dest='nocross', help='Don\'t cross device boundaries.' )
parser.add_option_group(group)

### Set the default index name
parser.set_defaults(index='remapid-%s.idx' % time.strftime('%Y%m%d-%H%M', time.localtime()))

(options, args) = parser.parse_args()

subcommand = args[0]
if args[0] not in subcommands:
    print >>sys.stderr, 'ERROR: Subcommand \'%s\' unknown, should be one of %s.' % (args[0], subcommands)
    sys.exit(1)


### INDEX mode
if subcommand == 'index':

    parents = args[1:]

    ### Make a list of excluded (mount) devices:
    excluded_devices = find_excluded_devices()

    for parent in parents:
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
#                    print path, s.st_uid, s.st_gid
                except OSError, e:
                    print >>sys.stderr, 'WARNING: %s' % e

                if s.st_uid in uidmap.keys():
                    debug('DEBUG: Found path %s owned by uid %d' % (path, s.st_uid))
                    if s.st_uid not in store['uid'].keys():
                        store['uid'][s.st_uid] = [ path ]
                    else:
                        store['uid'][s.st_uid].append(path)

                if s.st_gid in gidmap.keys():
                    debug('DEBUG: Found path %s owned by gid %d' % (path, s.st_gid))
                    if s.st_gid not in store['gid'].keys():
                        store['gid'][s.st_gid] = [ path ]
                    else:
                        store['gid'][s.st_gid].append(path)

    store['duration'] = time.clock()
    print >>sys.stderr, 'Total time:', store['duration'], 'secs'
    print store

    ### FIXME: Handle the case where the file already exists using tempfile
    ### Dump database
    try:
        pickle.dump(store, open(options.index, 'wb'))
    except:
        print >>sys.stderr, 'ERROR: Unable to dump database %s !' % options.index
        raise