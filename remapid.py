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

def info(level, msg):
    if options.verbose >= level:
        print msg

def lchown(path, uid=None, gid=None):
    if options.verbose > 0:
        if uid is None and gid is not None:
            info(1, 'Set path %s to gid %d' % (path, gid))
        elif uid is not None and gid is None:
            info(1, 'Set path %s to uid %d' % (path, uid))
        elif uid is not None and gid is not None:
            info(1, 'Set path %s to uid %d and gid to %d' % (path, uid, gid))
        else:
            raise 'Should not happen !'

    if options.test:
        return

    if uid == None:
        uid = os.lstat(path).st_uid
    if gid == None:
        gid = os.lstat(path).st_gid

    try:
        os.lchown(path, uid, gid)
    except OSError, e:
        print >>sys.stderr, 'WARNING: %s' % e


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
parser.add_option( '-t', '--test', action='store_true',
    dest='test', help='Test the run without actually changing anything.' )
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
if subcommand not in subcommands:
    print >>sys.stderr, 'ERROR: Subcommand \'%s\' unknown, should be one of %s.' % (args[0], subcommands)
    sys.exit(1)


### INDEX mode
if subcommand == 'index':

    if len(args) < 2:
        parents = [ os.getcwd(), ]
    else:
        parents = args[1:]

    store = {
      'parents': parents,
      'version': FORMAT_VERSION,
      'start': time.localtime(),
      'uid': { },
      'gid': { },
    }

    ### Make a list of excluded (mount) devices:
    excluded_devices = find_excluded_devices()

    retained_path_count = 0
    total_path_count = 0

    for parent in parents:

        if options.verbose > 0:
            print 'Processing %s' % parent

        for root, dirs, files in os.walk(parent, topdown=False):

            ### For speed, drop every root that is on an excluded device
            if os.lstat(root).st_dev in excluded_devices:
                continue

            ### Find paths that require remapping and store them
            for path in dirs + files:
                ### Make path absolute
                path = os.path.join(root, path)
                total_path_count += 1

                try:
                    s = os.lstat(path)
#                    print path, s.st_uid, s.st_gid
                except OSError, e:
                    print >>sys.stderr, 'WARNING: %s' % e

                if s.st_uid in uidmap.keys():
                    info(2, 'Found path %s owned by uid %d' % (path, s.st_uid))
                    if s.st_uid not in store['uid'].keys():
                        store['uid'][s.st_uid] = [ path ]
                    else:
                        store['uid'][s.st_uid].append(path)
                    retained_path_count += 1

                if s.st_gid in gidmap.keys():
                    info(2, 'Found path %s owned by gid %d' % (path, s.st_gid))
                    if s.st_gid not in store['gid'].keys():
                        store['gid'][s.st_gid] = [ path ]
                    else:
                        store['gid'][s.st_gid].append(path)
                    retained_path_count += 1

    store['duration'] = time.clock()
    store['stop'] = time.localtime()
    store['uidmap'] = uidmap
    store['gidmap'] = gidmap

    if options.debug:
        print '--------'
        print store
        print '--------'

    ### FIXME: Handle the case where the file already exists using tempfile
    ### Dump database
    try:
        pickle.dump(store, open(options.index, 'wb'))
    except:
        print >>sys.stderr, 'ERROR: Unable to dump index %s !' % options.index
        raise

    print >>sys.stderr, 'Index file written to %s' % options.index

    if options.verbose > 0:
        print >>sys.stderr, 'Number of paths retained:', retained_path_count
        print >>sys.stderr, 'Total number of paths processed:', total_path_count
        print >>sys.stderr, 'Total time:', store['duration'], 'secs'


if subcommand in ('status', 'remap', 'restore'):

    ### Open database (if exists and consistent)
    if os.path.lexists(options.index):
        try:
            store = pickle.load(open(options.index, 'rb'))
        except:
            print >>sys.stderr, 'WARNING: Problem reading from database %s, dropping' % database
    else:
        print >>sys.stderr, 'ERROR: Index file %s could not be found.' % options.index
        sys.exit(1)


### STATUS mode
if subcommand == 'status':

    print 'Index file %s' % options.index
    print

    print '  Version:', store['version']
    print '  Date:', time.strftime("%a, %d %b %Y %H:%M:%S +0000", store['start'])
    print '  Duration:', store['duration'], 'secs'


### REMAP mode
if subcommand == 'remap':

    ### Remap ownership based on stored uidmap/gidmap
    for uid in store['uidmap'].keys():
        if uid not in store['uid'].keys(): continue
        for path in store['uid'][uid]:
            lchown(path, uid=uidmap[uid])

    for gid in store['gidmap'].keys():
        if gid not in store['gid'].keys(): continue
        for path in store['gid'][gid]:
            lchown(path, gid=gidmap[gid])


### RESTORE mode
if subcommand == 'restore':

    ### Restore ownership based on stored ownerships
    for uid in store['uid'].keys():
        for path in store['uid'][uid]:
            lchown(path, uid=uid)

    for gid in store['gid'].keys():
        for path in store['gid'][gid]:
            lchown(path, gid=gid)
