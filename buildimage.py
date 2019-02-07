#!/usr/bin/env python3
import sys
import os
import re
import collections
import subprocess
import gzip
import json

#---------------------------------------------------------------------------
# I Am Not A Shell Script

def _call(shellcmd):
    print('--- ' + shellcmd)
    return subprocess.check_output(shellcmd, shell=True).strip().decode('utf-8')

#---------------------------------------------------------------------------

class Image:
    # Partitions
    BOOT = '1'
    ROOT1 = '2'
    ROOT2 = '3'

    def __init__(self, version, variant, path, name):
        self.version = version
        self.variant = variant
        self.original_path = path
        self.original_name = name
        self.name = os.path.splitext(name)[0] # discard the `.gz` part
        self.loopdev = None
        self.partitions = None
        self.mounted = set()

    def __repr__(self):
        return 'ImageSource(%s,%s)' % (self.version, self.variant)

    def decompress(self):
        if os.path.exists(self.name):
            return
        _call('gzip -dc %s > %s.tmp' % (self.original_path, self.name))
        _call('mv %s.tmp %s' % (self.name, self.name))

    def attach(self):
        if self.loopdev:
            raise Exception('Already attached %s to %s' % (self.name, self.loopdev))
        self.loopdev = _call('sudo losetup -f')
        _call('sudo losetup --partscan %s %s' % (self.loopdev, self.name))
        print('attached %s to %s' % (self.name, self.loopdev))
        self.partitions = \
            [p[len(self.loopdev)+1:] for p in _call('ls %sp*' % (self.loopdev,)).split()]
        print(self.partitions)

    def detach(self):
        for p in set(self.mounted):
            self.unmount(p)
        _call('sudo losetup -d %s' % (self.loopdev,))
        print('detached %s from %s' % (self.name, self.loopdev))
        self.loopdev = None

    def _mountpoint(self, partition):
        return 'mnt%s' % (partition,)

    def mount(self, partition):
        mnt = self._mountpoint(partition)
        try:
            os.mkdir(mnt)
        except FileExistsError:
            pass
        _call('sudo mount -o loop,rw %sp%s %s' % (self.loopdev, partition, mnt))
        self.mounted.add(partition)
        return mnt

    def unmount(self, partition):
        mnt = self._mountpoint(partition)
        _call('sudo umount %s' % (mnt,))
        try:
            os.rmdir(mnt)
        except FileNotFoundError:
            pass
        self.mounted.remove(partition)

#---------------------------------------------------------------------------

imagedir = os.path.expanduser(os.getenv('IMAGEDIR') or "~/dev/fruit/public/fruitos/release/images")

# Find all the images
images = set()
imagere = re.compile(r'^fruitos-([0-9.]+)-raspberrypi(.+)\.img\.gz$')
for f in os.scandir(imagedir):
    m = imagere.match(f.name)
    if not m:
        continue
    images.add(Image(m[1], m[2], f.path, f.name))

# Decompress them
for img in images:
    img.decompress()

# Extract a fruit.json, if there isn't already one here
if not os.path.exists('fruit.json'):
    arbitrary = list(images)[0]
    arbitrary.attach()
    mnt = arbitrary.mount(Image.BOOT)
    _call('cp %s/fruit.json .' % (mnt,))
    arbitrary.detach()

# Check it to see if it has been configured yet
with open('fruit.json', 'rt') as f:
    config = json.load(f)
    pk = config.get('public-key', None)
    if not pk:
        print('Please edit fruit.json and rerun this script.')
        sys.exit(1)

print('About to update %d images for pk %s:' % (len(images), pk))
for img in images:
    print(' - ' + repr(img))
print('Hit ENTER to continue, Ctrl-C to abandon')
input()

for img in images:
    img.attach()
    mnt = img.mount(Image.BOOT)
    _call('sudo cp fruit.json %s' % (mnt,))
    img.detach()

print('Images updated! Flash away!')
