"""Read the installed source's GTK API without importing the application."""
from pathlib import Path
import re


def gtk_api(root, pkgdata=None):
	root = Path(root)
	candidates = [root / 'usr/lib/python3/dist-packages/drawing/main.py']
	if pkgdata is not None:
		candidates.append(Path(pkgdata) / 'drawing/main.py')
	for source in candidates:
		if source.is_file():
			match = re.search(
				r'''^gi\.require_version\(['"]Gtk['"],\s*['"](3\.0|4\.0)['"]\)''',
				source.read_text(), re.MULTILINE)
			if match is None:
				raise ValueError(f'No supported GTK API declaration in {source}')
			return match[1]
	raise FileNotFoundError('The staged Drawing Python package is missing')
