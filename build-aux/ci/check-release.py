#!/usr/bin/env python3
"""Verify a release tag identifies an accepted, versioned source tree."""
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


tag = sys.argv[1]
match = re.fullmatch(r'v?(\d+\.\d+\.\d+)', tag)
if not match:
	raise SystemExit('Release tag must be a stable version, optionally prefixed with v')
version = json.loads(subprocess.check_output(['meson', 'introspect', '--projectinfo', 'build']))['version']
if version != match[1]:
	raise SystemExit(f'Tag {tag} does not match Meson version {version}')
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
tag_commit = subprocess.check_output(['git', 'rev-parse', f'refs/tags/{tag}^{{commit}}'], text=True).strip()
if tag_commit != commit:
	raise SystemExit('Checkout differs from tag target')
ancestry = subprocess.run(
	['git', 'merge-base', '--is-ancestor', commit, 'refs/remotes/origin/master'],
	stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
if ancestry.returncode != 0:
	raise SystemExit('Tag must belong to protected master history')
metadata = ET.parse('data/com.github.maoschanz.drawing.appdata.xml.in')
if not any(r.get('version') == version for r in metadata.findall('./releases/release')):
	raise SystemExit(f'AppStream metadata lacks release {version}')
with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
	output.write(f'commit={commit}\n')
print(f'Validated {tag}: {commit}, version {version}')
