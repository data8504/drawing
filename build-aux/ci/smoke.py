#!/usr/bin/env python3
"""Open and render a fresh image using the installed application's resources."""
import argparse
import os
from pathlib import Path
import runpy
import sys
import traceback

parser = argparse.ArgumentParser()
parser.add_argument('--root', type=Path, default=Path('/'))
args = parser.parse_args()
# The caller must provide a private display, session bus and memory settings.
assert os.environ.get('GSETTINGS_BACKEND') == 'memory'
launcher = runpy.run_path(str(args.root / 'usr/bin/drawing'))
pkgdata = args.root / launcher['pkgdatadir'].lstrip('/')
sys.path.insert(0, str(pkgdata))
sys.path.insert(0, str(args.root / 'usr/lib/python3/dist-packages'))
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gio, GLib, Gtk

if not Gtk.init_check([])[0]:
	raise SystemExit('GTK display is unavailable')

resource = Gio.Resource.load(str(pkgdata / 'drawing.gresource'))
resource._register()
from drawing.main import Application

# Dismiss the first-run help prompt through temporary, memory-only settings.
# Otherwise its nested modal loop prevents a non-interactive smoke from exiting.
settings = Gio.Settings.new('com.github.maoschanz.drawing')
settings.set_string('last-version', launcher['VERSION'])
settings.set_int('default-width', 32)
settings.set_int('default-height', 32)

Application.APP_ID += '.Smoke' + str(os.getpid())
app = Application(launcher['VERSION'])
failed = True

def check_window():
	global failed
	try:
		windows = app.get_windows()
		assert len(windows) == 1, 'Expected one fresh window'
		image = windows[0].get_active_image()
		assert image is not None, 'Fresh window has no image'
		surface = image.get_surface()
		assert surface.get_width() > 0 and surface.get_height() > 0
		assert windows[0].get_mapped(), 'Window did not map'
		failed = False
		print('Installed Drawing opened a window and initialized its image surface.')
	except Exception:
		traceback.print_exc()
	finally:
		app.quit()
	return GLib.SOURCE_REMOVE

GLib.timeout_add(1500, check_window)
status = app.run(['drawing', '--new-window'])
sys.exit(status or int(failed))
