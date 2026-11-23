#!/usr/bin/env python3
"""Publish complete, verified build outputs as an immutable GitHub release."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import quote


def api(path, payload=None):
	cmd = ['gh', 'api', path]
	if payload is not None:
		cmd += ['--method', 'POST', '--input', '-']
	result = subprocess.run(cmd, input=json.dumps(payload) if payload else None,
	                        text=True, capture_output=True, check=True)
	return json.loads(result.stdout) if result.stdout else None


repo = os.environ['GH_REPO']
tag = os.environ['RELEASE_TAG']
commit = os.environ['RELEASE_COMMIT']
assert re.fullmatch(r'v?\d+\.\d+\.\d+', tag)
assert re.fullmatch(r'[0-9a-f]{40}', commit)
endpoint = f'repos/{repo}'
if not api(f'{endpoint}/immutable-releases')['enabled']:
	raise SystemExit('Repository release immutability must be enabled before publication')
output = Path('release-assets')
output.mkdir()
for path in sorted(Path(sys.argv[1]).glob('*/*')):
	if not path.is_file():
		continue
	destination = output / path.name
	if destination.exists() and destination.read_bytes() != path.read_bytes():
		raise SystemExit(f'Conflicting matrix assets: {path.name}')
	shutil.copyfile(path, destination)
expected_distributions = {'ubuntu24.04', 'ubuntu26.04'}
manifest_paths = list(output.glob('build-*.json'))
if len(manifest_paths) != 2:
	raise SystemExit('Both native build manifests are required')
for path in manifest_paths:
	manifest = json.loads(path.read_text())
	assert manifest['commit'] == commit and manifest['version'] == tag.removeprefix('v')
	expected_distributions.remove(manifest['distribution'])
	assert (output / f"drawing_{manifest['package_version']}_all.deb").is_file()
assert not expected_distributions
assert (output / f'drawing-{tag.removeprefix("v")}.tar.gz').is_file()
digests = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())}
(output / 'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name, digest in digests.items()))
digests['SHA256SUMS'] = hashlib.sha256((output / 'SHA256SUMS').read_bytes()).hexdigest()
# Check the immutable tag still names the commit checked in both native jobs.
assert api(f'{endpoint}/commits/{quote(tag, safe="")}')['sha'] == commit
existing = subprocess.run(['gh', 'api', f'{endpoint}/releases/tags/{quote(tag, safe="")}'],
                          text=True, capture_output=True)
if existing.returncode:
	# Authentication/network failures must not be mistaken for "no release".
	if 'HTTP 404' not in existing.stderr:
		raise SystemExit(existing.stderr)
	release = api(f'{endpoint}/releases', {
		'tag_name': tag, 'target_commitish': commit, 'name': f'Drawing {tag.removeprefix("v")}',
		'draft': True, 'prerelease': False,
		'body': f'Builds of Drawing {tag.removeprefix("v")} from `{commit}`.\n\n'
		        'Use the package matching your Ubuntu release. SHA256SUMS and the '
		        'build manifests identify the source and packaged build environment.\n'
	})
else:
	release = json.loads(existing.stdout)


def verify_assets(release):
	assert {a['name'] for a in release['assets']} == set(digests), 'Release asset list differs'
	with tempfile.TemporaryDirectory() as directory:
		subprocess.run(['gh', 'release', 'download', tag, '--dir', directory], check=True)
		for name, digest in digests.items():
			assert hashlib.sha256((Path(directory) / name).read_bytes()).hexdigest() == digest, name


if release['draft']:
	# A retry may finish this exact draft. Never replace an uploaded asset; verify
	# its bytes first. An unrelated or stale draft fails the final asset-set check.
	assets = {a['name']: a for a in release['assets']}
	for name in digests:
		if name not in assets:
			subprocess.run(['gh', 'release', 'upload', tag, str(output / name)], check=True)
	release = api(f'{endpoint}/releases/{release["id"]}')
	verify_assets(release)
	assert api(f'{endpoint}/commits/{quote(tag, safe="")}')['sha'] == commit
	cmd = ['gh', 'api', '--method', 'PATCH', f'{endpoint}/releases/{release["id"]}', '--input', '-']
	release = json.loads(subprocess.check_output(cmd,
	                     input=json.dumps({'draft': False, 'make_latest': 'true'}), text=True))
else:
	verify_assets(release)
assert release['immutable'] and not release['draft'], 'Publication is not immutable'
assert api(f'{endpoint}/commits/{quote(tag, safe="")}')['sha'] == commit
assert api(f'{endpoint}/releases/latest')['id'] == release['id'], 'Release is not latest'
print(f'Verified immutable release {tag} at {commit}: {release["html_url"]}')
