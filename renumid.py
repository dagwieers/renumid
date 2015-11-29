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
import pprint
from datetime import datetime
import yaml
import fnmatch
import socket

VERSION = '0.1'
FORMAT_VERSION = 1

hostname = socket.gethostbyaddr(socket.gethostname())[0]

subcommands = ('index', 'status', 'renumber', 'restore')

def info(level, msg):
    if options.verbosity >= level:
        print >>sys.stderr, msg

def warn(msg):
    print >>sys.stderr, 'WARNING:', msg

def error(rc, msg):
    print >>sys.stderr, 'ERROR:', msg
    sys.exit(rc)

def lchown(path, uid=None, gid=None):
    '''Change ownership of files, report or test.'''
    if options.verbosity > 0:
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
        warn(e)

def find_excluded_devices():
    ''' Return a list of file system devices that are excluded '''
    excluded_devices = []
    for l in open('/proc/mounts', 'r'):
        (dev, mp, fstype, opts, x, y) = l.split()
        s = os.statvfs(mp)
        if s.f_blocks == 0:
            info(3, 'Exclude pseudo filesystem %s of type %s' % (mp, fstype))
            excluded_devices.append(os.lstat(mp).st_dev)
        elif included_fstypes and fstype not in included_fstypes:
            info(3, 'Exclude filesystem %s of type %s' % (mp, fstype))
            excluded_devices.append(os.lstat(mp).st_dev)
    return excluded_devices

def process_idmap(idmap):
    global hostname

    uidmap = dict()
    gidmap = dict()

    for key in idmap.keys():
        if key == 'uidmap':
            uidmap.update(idmap['uidmap'])
        elif key == 'gidmap':
            gidmap.update(idmap['gidmap'])
        elif fnmatch.fnmatch(hostname, key):
            if 'uidmap' in idmap[key].keys():
                uidmap.update(idmap[key]['uidmap'])
            if 'gidmap' in idmap[key].keys():
                gidmap.update(idmap[key]['gidmap'])

    return uidmap, gidmap


parser = optparse.OptionParser(
    version='%prog '+VERSION,
    description='''Subcommands:                                                                   
  index          create a file system index of impacted paths using a map       
  status         show a status report of impacted paths and affected UIDs/GIDs  
  renumber       renumber the impacted paths according to the stored map        
  restore        restore the original situation using the file system index     
'''
)
parser.add_option('-f', '--file', action='store',
                  dest='index', help='index file to create/use' )
parser.add_option('-v', '--verbose', action='count',
                  dest='verbosity', help='be more and more and more verbose' )

group1 = optparse.OptionGroup(parser, "Index options",
                              "These options only apply to Index mode")
group1.add_option('-m', '--map', action='store',
                  dest='map', help='map file to use for UID/GID renumbering' )
group1.add_option('-T', '--fstypes', action='store',
                  dest='fstypes', help='list of filesystem types to index' )
#group1.add_option('-x', '--one-file-system', action='store_true',
#                  dest='nocross', help='Don\'t cross device boundaries' )
parser.add_option_group(group1)

group2 = optparse.OptionGroup(parser, "Renumber/Restore options",
                              "These options only apply to Renumber and Restore mode")
group2.add_option('-t', '--test', action='store_true',
                  dest='test', help='test the run without actually changing anything' )
parser.add_option_group(group2)

parser.set_usage('Usage: %prog [subcommand] [options]')

### Set the default index name
parser.set_defaults(index=None)
parser.set_defaults(map=None)
parser.set_defaults(fstypes='ext3,ext4,xfs')

(options, args) = parser.parse_args()

if not args:
    parser.error('Subcommand not provided, should be one of %s' % (subcommands,))

subcommand = args[0]
if subcommand not in subcommands:
    parser.error('Subcommand \'%s\' unknown, should be one of %s' % (subcommand, subcommands))

if subcommand in ('index', 'renumber', 'restore'):
    if os.geteuid() != 0:
        error(12, 'Subcommand \'%s\' should be run as root' % subcommand)

included_fstypes = options.fstypes.split(',')

### INDEX mode
if subcommand == 'index':

    if options.map is None:
        parser.error('Option -m/--map is required in Index mode')

    # Set default Index file name (if missing)
    if options.index is None:
        options.index = 'renumid-%s.idx' % time.strftime('%Y%m%d-%H%M', time.localtime())

    if len(args) < 2:
        parents = [ os.getcwd(), ]
    else:
        parents = args[1:]

    try:
        idmap = yaml.load(file(options.map, 'r'))
    except IOError, e:
        error(17, e)

    uidmap, gidmap = process_idmap(idmap)

    store = {
      'parents': parents,
      'version': FORMAT_VERSION,
      'start': datetime.now(),
      'map': os.path.abspath(options.map),
      'uid': { },
      'gid': { },
    }

    ### Make a list of excluded (mount) devices:
    excluded_devices = find_excluded_devices()

    uid_paths_retained = 0
    gid_paths_retained = 0
    paths_scanned = 0

    for parent in parents:

        info(1, 'Processing parent %s' % parent)

        for root, dirs, files in os.walk(parent, topdown=False):

            ### For speed, drop every root that is on an excluded device
            if os.lstat(root).st_dev in excluded_devices:
                continue

            info(2, 'Processing root %s' % root)

            ### Find paths that require renumbering and store them
            for path in dirs + files:

                paths_scanned += 1

                ### Make path absolute
                path = os.path.join(root, path)
                info(3, 'Processing path %s' % path)

                try:
                    s = os.lstat(path)
                except OSError, e:
                    warn(e)

                if s.st_uid in uidmap.keys():
                    info(2, 'Found path %s owned by uid %d' % (path, s.st_uid))
                    if s.st_uid not in store['uid'].keys():
                        store['uid'][s.st_uid] = [ path ]
                    else:
                        store['uid'][s.st_uid].append(path)
                    uid_paths_retained += 1

                if s.st_gid in gidmap.keys():
                    info(2, 'Found path %s owned by gid %d' % (path, s.st_gid))
                    if s.st_gid not in store['gid'].keys():
                        store['gid'][s.st_gid] = [ path ]
                    else:
                        store['gid'][s.st_gid].append(path)
                    gid_paths_retained += 1

    store['stop'] = datetime.now()
    store['runtime'] = store['stop'] - store['start']
    store['cputime'] = time.clock()
    store['uidmap'] = uidmap
    store['gidmap'] = gidmap
    store['uid_paths_retained'] = uid_paths_retained
    store['gid_paths_retained'] = gid_paths_retained
    store['paths_scanned'] = paths_scanned

    if options.verbosity > 3:
        print '--------'
        pprint.pprint(store)
        print '--------'

    ### FIXME: Handle the case where the file already exists using tempfile
    ### Dump store
    try:
        pickle.dump(store, open(options.index, 'wb'))
    except Exception, e:
        error(13, 'Unable to dump Index file %s !\n%s' % (options.index, e))

    if options.verbosity == 0:
        sys.exit(0)


if subcommand in ('status', 'renumber', 'restore'):

    if options.index is None:
        parser.error('Option -f/--file is required in %s mode' % subcommand.title())

    ### Open index file (if exists and consistent)
    if os.path.lexists(options.index):
        try:
            store = pickle.load(open(options.index, 'rb'))
        except Exception, e:
            error(14, 'Problem reading from Index file %s.\n%s' % (options.index, e))
    else:
        error(15, 'Index file %s could not be found.' % options.index)


### STATUS mode
if subcommand in ('index', 'status'):

    print 'Index file name %s' % options.index
    print

    print '  Version:', store['version']
    print '  Date:', store['start'].strftime("%a, %d %b %Y %H:%M:%S +0000")
    print '  Parents:', ' '.join(store['parents'])
    print

    print 'Indexing stats'
    print

    print '  Number of UID paths retained:', store['uid_paths_retained']
    print '  Number of GID paths retained:', store['gid_paths_retained']
    print '  Total number of paths processed:', store['paths_scanned']
    print '  Total cputime: %.2f secs' % store['cputime']
    print '  Total runtime: %.2f secs' % (store['runtime'].seconds + store['runtime'].microseconds * 1.0 / 1000000)
    print

    if options.verbosity > 3:
        print '--------'
        pprint.pprint(store)
        print '--------'


### RENUMBER mode - renumber ownership based on stored uidmap/gidmap
if subcommand == 'renumber':

    for uid in store['uidmap'].keys():
        if uid not in store['uid'].keys(): continue
        for path in store['uid'][uid]:
            lchown(path, uid=store['uidmap'][uid])

    for gid in store['gidmap'].keys():
        if gid not in store['gid'].keys(): continue
        for path in store['gid'][gid]:
            lchown(path, gid=store['gidmap'][gid])


### RESTORE mode - restore based on stored ownerships
if subcommand == 'restore':

    for uid in store['uid'].keys():
        for path in store['uid'][uid]:
            lchown(path, uid=uid)

    for gid in store['gid'].keys():
        for path in store['gid'][gid]:
            lchown(path, gid=gid)
