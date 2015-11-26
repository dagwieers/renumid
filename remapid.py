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

debug = True
info = True
parent = '.'
if len(sys.argv) > 1:
    parent = sys.argv[1]

def fstype(root):
    ''' Return file system type of a file system root'''
    for l in open('/proc/mounts', 'r'):
        (dev, mp, fstype, opts, x, y) = l.split()
        if mp == root:
            return fstype
    else:
        raise Exception, 'Path %s is not a known file system'

for root, dirs, files in os.walk(parent, topdown=True):
    for path in dirs + files:
        ### Make path absolute
        path = os.path.join(root, path)

        try:
            s = os.lstat(path)
            print path, s.st_uid, s.st_gid
        except OSError, e:
            print >>sys.stderr, 'WARNING: %s' % e