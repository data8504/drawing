#!/usr/bin/env python3

import gettext
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk

os.environ['GSETTINGS_BACKEND'] = 'memory'
source = Path(__file__).resolve().parents[1]
package = types.ModuleType('drawing')
package.__path__ = [str(source / 'src')] + sorted({
	str(p.parent) for p in (source / 'src').rglob('*.py')
})
sys.modules['drawing'] = package
gettext.install('drawing')


class SaveStateTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		if not Gtk.init_check([])[0]:
			raise RuntimeError('A private GTK display is required')
		Gio.Resource.load(sys.argv[1])._register()
		cls.schemas = tempfile.TemporaryDirectory()
		shutil.copy(source / 'data/com.github.maoschanz.drawing.gschema.xml',
			cls.schemas.name)
		subprocess.run(['glib-compile-schemas', cls.schemas.name], check=True)
		os.environ['GSETTINGS_SCHEMA_DIR'] = cls.schemas.name
		settings = Gio.Settings.new('com.github.maoschanz.drawing')
		settings.set_string('last-version', '1.2.0-test')
		settings.set_int('default-width', 32)
		settings.set_int('default-height', 16)
		from drawing.main import Application
		Application.APP_ID += '.SaveTest' + str(os.getpid())
		cls.app = Application('1.2.0-test')

	@classmethod
	def tearDownClass(cls):
		cls.app.quit()
		cls.schemas.cleanup()

	def setUp(self):
		self.callback_errors = []
		previous_hook = sys.excepthook
		def capture(*info):
			self.callback_errors.append(info[1])
			previous_hook(*info)
		sys.excepthook = capture
		self.addCleanup(setattr, sys, 'excepthook', previous_hook)
		from drawing.window import DrWindow
		self.folder = tempfile.TemporaryDirectory()
		self.addCleanup(self.folder.cleanup)
		self.path = Path(self.folder.name) / 'original.png'
		pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 32, 16)
		pixbuf.fill(0xffffffff)
		pixbuf.savev(str(self.path), 'png', [], [])
		self.window = DrWindow(application=self.app)
		self.window.init_window_content_async({'gfile': None, 'get_cb': False})
		self.window._build_new_tab(gfile=Gio.File.new_for_path(str(self.path)))
		self.window.show_all()
		self.image = self.window.get_active_image()
		self.manager = self.window.saving_manager
		self.window.tools['pencil'].select_flowbox_child()
		self.window.options_manager.set_left_color(
			Gdk.RGBA(red=1, green=0, blue=0, alpha=1))
		self.drain()
		self.image.hide_reload_message()

	def tearDown(self):
		self.window.destroy()
		self.drain()
		self.assertEqual(self.callback_errors, [])

	def drain(self):
		context = GLib.MainContext.default()
		while context.pending():
			context.iteration(False)

	def pixels(self):
		self.image.surface.flush()
		return bytes(self.image.surface.get_data())

	def edit(self):
		event = Gdk.EventButton()
		event.type = Gdk.EventType.BUTTON_PRESS
		event.button = 1
		event.x = (10 - self.image.scroll_x) * self.image.zoom_level
		event.y = (10 - self.image.scroll_y) * self.image.zoom_level
		event.state = Gdk.ModifierType(0)
		self.image.on_press_on_area(self.image._drawing_area, event)
		event.type = Gdk.EventType.BUTTON_RELEASE
		self.image.on_release_on_area(self.image._drawing_area, event)

	def test_failed_save_as_preserves_document(self):
		self.edit()
		before = self.pixels()
		bad_path = Path(self.folder.name) / 'directory.png'
		bad_path.mkdir()
		with patch.object(self.manager, '_file_chooser_save',
			return_value=Gio.File.new_for_path(str(bad_path))):
			self.assertFalse(self.manager.save_current_image(False, True,
				False, True))
		self.assertEqual(self.image.get_file_path(), str(self.path))
		self.assertEqual(self.pixels(), before)
		self.assertFalse(self.image.is_saved())

	def test_delayed_notifications_preserve_later_edit(self):
		old_monitor = self.image._gfile_monitor
		self.assertTrue(self.manager.save_current_image(False, False,
			False, True))
		self.assertTrue(self.image.is_saved())
		self.edit()
		edited = self.pixels()
		# Deliver the old self-write notification after the new edit, as GIO
		# can do. The callback must not restore a previous disk snapshot.
		self.image.reveal_reload_message(old_monitor, None, None,
			Gio.FileMonitorEvent.CHANGES_DONE_HINT)
		self.image.reveal_reload_message(self.image._gfile_monitor, None,
			None, Gio.FileMonitorEvent.CHANGES_DONE_HINT)
		self.assertEqual(self.pixels(), edited)
		self.assertFalse(self.image.is_saved())
		self.assertFalse(self.image.reload_info_bar.get_visible())

		# A real external write must offer an explicit reload without
		# replacing the editor's unsaved pixels or marking them as saved.
		external = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True,
			8, 32, 16)
		external.fill(0x0000ffff)
		external.savev(str(self.path), 'png', [], [])
		deadline = time.monotonic() + 5
		while not self.image.reload_info_bar.get_visible() \
		and time.monotonic() < deadline:
			self.drain()
			time.sleep(.01)
		self.assertTrue(self.image.reload_info_bar.get_visible())
		self.assertEqual(self.pixels(), edited)
		self.assertFalse(self.image.is_saved())
		self.image.reload_from_disk()
		self.assertNotEqual(self.pixels(), edited)
		self.assertEqual(bytes(self.image.main_pixbuf.get_pixels()),
			bytes(external.get_pixels()))
		self.assertTrue(self.image.is_saved())

	def test_failed_replacement_cancels_old_file_monitor(self):
		old_monitor = self.image._gfile_monitor
		malformed = Path(self.folder.name) / 'broken.png'
		malformed.write_text('not an image')
		self.image.try_load_file(Gio.File.new_for_path(str(malformed)))
		self.assertIsNone(self.image.gfile)
		self.assertIsNone(self.image._gfile_monitor)
		self.assertTrue(old_monitor.is_cancelled())
		self.image.reveal_reload_message(old_monitor, None, None,
			Gio.FileMonitorEvent.CHANGES_DONE_HINT)
		self.assertFalse(self.image.reload_info_bar.get_visible())

	def test_alpha_cancellation_does_not_report_a_completed_save(self):
		from drawing.saving_manager import WantToCancelException
		self.edit()
		before = self.pixels()
		destination = Path(self.folder.name) / 'cancelled.jpg'
		self.window.gsettings.set_string('replace-alpha', 'ask')
		with patch.object(self.manager, '_file_chooser_save',
			return_value=Gio.File.new_for_path(str(destination))), \
		patch.object(self.manager, '_ask_overwrite_alpha',
			side_effect=WantToCancelException):
			self.assertFalse(self.manager.save_current_image(False, True,
				False, True))
		self.assertFalse(destination.exists())
		self.assertEqual(self.image.get_file_path(), str(self.path))
		self.assertEqual(self.pixels(), before)
		self.assertFalse(self.image.is_saved())

	def test_export_preserves_document_identity_and_dirty_state(self):
		self.edit()
		before = self.pixels()
		export = Path(self.folder.name) / 'export.png'
		with patch.object(self.manager, '_file_chooser_save',
			return_value=Gio.File.new_for_path(str(export))):
			self.assertTrue(self.manager.save_current_image(True, True,
				False, True))
		self.assertTrue(export.is_file())
		self.assertEqual(self.image.get_file_path(), str(self.path))
		self.assertEqual(self.pixels(), before)
		self.assertFalse(self.image.is_saved())


if __name__ == '__main__':
	unittest.main(argv=[sys.argv[0]])
