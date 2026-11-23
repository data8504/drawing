#!/usr/bin/env python3
"""Package the validated Meson staging tree, without rebuilding it."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def git(*args):
	return subprocess.check_output(['git', *args], text=True).strip()


parser = argparse.ArgumentParser()
parser.add_argument('stage', type=Path)
parser.add_argument('output', type=Path)
parser.add_argument('--distribution', required=True)
args = parser.parse_args()
assert re.fullmatch(r'ubuntu(?:24|26)\.04', args.distribution)
info = json.loads(subprocess.check_output(['meson', 'introspect', '--projectinfo', 'build']))
version = info['version']
assert re.fullmatch(r'\d+\.\d+\.\d+(?:-dev)?', version), version
commit = git('rev-parse', 'HEAD')
epoch = int(git('show', '-s', '--format=%ct', 'HEAD'))
args.output.mkdir(parents=True, exist_ok=True)
deb_version = version.replace('-dev', '~dev') + '-1+' + args.distribution
# Match Debian/Ubuntu's existing runtime module location.
modules = args.stage / 'usr/share/drawing/drawing'
pythonlib = args.stage / 'usr/lib/python3/dist-packages'
pythonlib.mkdir(parents=True)
shutil.move(str(modules), pythonlib / 'drawing')
doc = args.stage / 'usr/share/doc/drawing'
doc.mkdir(parents=True, exist_ok=True)
shutil.copyfile('debian/copyright', doc / 'copyright')
shutil.copyfile('LICENSE', doc / 'LICENSE')
control = args.stage / 'DEBIAN'
control.mkdir()
(control / 'control').write_text(f'''Package: drawing
Version: {deb_version}
Architecture: all
Maintainer: Matthew Hiltner <data8504@users.noreply.github.com>
Section: graphics
Priority: optional
Depends: gir1.2-gtk-3.0 (>= 3.24), python3-gi-cairo (>= 3.30), python3, dconf-gsettings-backend | gsettings-backend
Description: Simple drawing application for the GNOME desktop
 A continuation of Drawing, a basic image editor for the GNOME desktop.
''')
# Debian's file triggers update schema, icon and desktop caches on install/remove.
# No package-maintained user configuration or application data is modified.
for p in sorted(args.stage.rglob('*'), reverse=True):
	os.utime(p, (epoch, epoch), follow_symlinks=False)
os.utime(args.stage, (epoch, epoch))
package = args.output / f'drawing_{deb_version}_all.deb'
subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(args.stage), str(package)],
               env={**os.environ, 'SOURCE_DATE_EPOCH': str(epoch)}, check=True)
archive = args.output / f'drawing-{version}.tar.gz'
# Git fixes entry ordering and timestamps to the commit; gzip adds no wall-clock
# timestamp or host-specific filename. Include exactly this commit's tracked tree.
with archive.open('wb') as raw:
	with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed:
		compressed.write(subprocess.check_output(['git', 'archive', '--format=tar',
		                 f'--prefix=drawing-{version}/', commit]))
manifest = {'commit': commit, 'version': version, 'distribution': args.distribution,
            'source_date_epoch': epoch, 'package_version': deb_version,
            'packages': subprocess.check_output(['dpkg-query', '-W', '-f=${Package}\t${Version}\n',
                         'meson', 'ninja-build', 'python3', 'python3-gi-cairo',
                         'gir1.2-gtk-3.0'], text=True).splitlines()}
(args.output / f'build-{args.distribution}.json').write_text(json.dumps(manifest, indent=2) + '\n')
for p in sorted(args.output.iterdir()):
	if p.is_file() and p.name != 'SHA256SUMS':
		print(hashlib.sha256(p.read_bytes()).hexdigest(), p.name)
