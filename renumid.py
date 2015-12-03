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
import syslog
import gzip

VERSION = '0.1'
FORMAT_VERSION = 1

hostname = socket.gethostbyaddr(socket.gethostname())[0]

subcommands = ('index', 'status', 'renumber', 'restore')

def info(level, msg):
    if options.verbosity >= level:
        print >>sys.stderr, msg

def warn(msg):
    print >>sys.stderr, 'WARNING:', msg
    syslog.syslog(syslog.LOG_WARNING, 'WARNING: %s' % msg)

def error(rc, msg):
    print >>sys.stderr, 'ERROR:', msg
    syslog.syslog(syslog.LOG_ERR, 'ERROR: %s' % msg)
    sys.exit(rc)

def boottime():
    with open('/proc/stat') as f:
        for line in f:
            if line.startswith(b'btime '):
                return float(line.strip().split()[1])
        raise 'Boottime not found in /proc/stat'

def starttime():
    clock_ticks = os.sysconf('SC_CLK_TCK')
    values = open('/proc/%d/stat' % os.getpid()).read().split(b' ')
    return (float(values[21]) / clock_ticks) + boottime()

def lchown(path, uid=-1, gid=-1):
    '''Change ownership of files, report or test.'''
    if options.verbosity > 0:
        if uid is -1 and gid is not -1:
            info(1, 'Set path %s to gid %d' % (path, gid))
        elif uid is not -1 and gid is -1:
            info(1, 'Set path %s to uid %d' % (path, uid))
        elif uid is not -1 and gid is not -1:
            info(1, 'Set path %s to uid %d and gid to %d' % (path, uid, gid))
        else:
            raise 'Should not happen !'

    if options.test:
        return

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

def report_running():
    for entry in os.listdir('/proc'):
        if not entry.isdigit: continue
        try:
            s = os.lstat('/proc/%s' % entry)
        except OSError, e:
            pass

        if s.st_uid in uidmap.keys() and s.st_gid in gidmap.keys():
            name = os.path.basename(open('/proc/%s/cmdline' % entry).read().split('\0')[0])
            warn('Process %s [%s] is running as impacted uid %d and gid %d' % (name, entry, s.st_uid, s.st_gid))
        elif s.st_uid in uidmap.keys():
            name = os.path.basename(open('/proc/%s/cmdline' % entry).read().split('\0')[0])
            warn('Process %s [%s] is running as impacted uid %d' % (name, entry, s.st_uid))
        elif s.st_gid in gidmap.keys():
            name = os.path.basename(open('/proc/%s/cmdline' % entry).read().split('\0')[0])
            warn('Process %s [%s] is running as impacted gid %d' % (name, entry, s.st_gid))


parser = optparse.OptionParser(
    version='%prog '+VERSION,
    description='''Subcommands:                                                                   
  index          create a file system index of impacted paths using a map       
  status         show a status report of impacted paths and affected UIDs/GIDs  
  renumber       renumber the impacted paths according to the stored map        
  restore        restore the original situation using the index file            
'''
)
parser.add_option('-v', '--verbose', action='count',
                  dest='verbosity', help='be more and more and more verbose' )
parser.add_option('-f', '--file', action='store',
                  dest='index', help='index file to create/use' )

group1 = optparse.OptionGroup(parser, "Index options",
                              "These options only apply to Index mode")
group1.add_option('-m', '--map', action='store',
                  dest='map', help='map file to use for UID/GID renumbering' )
group1.add_option('-T', '--fstypes', action='store',
                  dest='fstypes', help='list of file system types to index' )
#group1.add_option('-x', '--one-file-system', action='store_true',
#                  dest='nocross', help='Don\'t cross device boundaries' )
parser.add_option_group(group1)

group2 = optparse.OptionGroup(parser, "Renumber/Restore options",
                              "These options only apply to Renumber and Restore mode")
group2.add_option('-t', '--test', action='store_true',
                  dest='test', help='test the run without actually changing anything' )
parser.add_option_group(group2)

parser.set_usage('Usage: %prog [subcommand] [options]')

parser.set_defaults(verbosity=0)
parser.set_defaults(index=None)
parser.set_defaults(map=None)
parser.set_defaults(fstypes='ext3,ext4,xfs')

(options, args) = parser.parse_args()

if not args:
    parser.error('Subcommand not provided, should be one of %s' % (subcommands,))

subcommand = args[0]
if subcommand not in subcommands:
    parser.error('Subcommand \'%s\' unknown, should be one of %s' % (subcommand, subcommands))

syslog.openlog('renumid')

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
        options.index = 'renumid-%s.idx.gz' % time.strftime('%Y%m%d-%H%M', time.localtime())

    if len(args) < 2:
        parents = [ os.getcwd(), ]
    else:
        parents = args[1:]

    try:
        idmap = yaml.load(file(options.map, 'r'))
    except IOError, e:
        error(17, e)

    uidmap, gidmap = process_idmap(idmap)

    report_running()

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

    syslog.syslog(syslog.LOG_INFO, 'File system scanning started. Index file being generated.')

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

    times = os.times()
    store['realtime'] = time.time() - starttime()
    store['usrtime'] = times[0]
    store['systime'] = times[1]
    store['stop'] = datetime.now()
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
        pickle.dump(store, gzip.open(options.index, 'wb'))
    except Exception, e:
        error(13, 'Unable to dump Index file %s !\n%s' % (options.index, e))

    syslog.syslog(syslog.LOG_INFO, 'Index file finished and written as: %s' % options.index)

    if options.verbosity == 0:
        print 'Index file written as: %s' % options.index
        sys.exit(0)


### Load the index file
if subcommand in ('status', 'renumber', 'restore'):

    if options.index is None:
        parser.error('Option -f/--file is required in %s mode' % subcommand.title())

    ### Open index file (if exists and consistent)
    if os.path.lexists(options.index):
        try:
            store = pickle.load(gzip.open(options.index, 'rb'))
        except Exception, e:
            ### Still support uncompressed pickle files
            try:
                store = pickle.load(open(options.index, 'rb'))
            except Exception, e:
                error(14, 'Problem reading from Index file %s.\n%s' % (options.index, e))
    else:
        error(15, 'Index file %s could not be found.' % options.index)

    if store['version'] != FORMAT_VERSION:
        error (16, 'The index file  has format version %d, while this tool expects version %d.' % (store['version'], FORMAT_VERSION))

    uidmap = store['uidmap']
    gidmap = store['gidmap']


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
    print '  Real time: %.2f secs' % store['realtime']
    print '  User time: %.2f secs' % store['usrtime']
    print '  System time: %.2f secs' % store['systime']
    print

    if options.verbosity > 3:
        print '--------'
        pprint.pprint(store)
        print '--------'


### RENUMBER mode - renumber ownership based on stored uidmap/gidmap
if subcommand == 'renumber':

    report_running()

    syslog.syslog(syslog.LOG_INFO, 'Renumbering files started.')

    for uid in store['uidmap'].keys():
        if uid not in store['uid'].keys(): continue
        for path in store['uid'][uid]:
            lchown(path, uid=store['uidmap'][uid])

    for gid in store['gidmap'].keys():
        if gid not in store['gid'].keys(): continue
        for path in store['gid'][gid]:
            lchown(path, gid=store['gidmap'][gid])

    syslog.syslog(syslog.LOG_INFO, 'Renumbering files finished.')

### RESTORE mode - restore based on stored ownerships
if subcommand == 'restore':

    syslog.syslog(syslog.LOG_INFO, 'Restoring files started.')

    for uid in store['uid'].keys():
        for path in store['uid'][uid]:
            lchown(path, uid=uid)

    for gid in store['gid'].keys():
        for path in store['gid'][gid]:
            lchown(path, gid=gid)

    syslog.syslog(syslog.LOG_INFO, 'Restoring files finished.')
