#!/usr/bin/env python3

import gettext
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk

# The installed package flattens these source directories.
source_dir = Path(__file__).resolve().parents[1] / 'src'
package = types.ModuleType('drawing')
package.__path__ = [str(source_dir)] + sorted({
	str(path.parent) for path in source_dir.rglob('*.py')
})
sys.modules['drawing'] = package
gettext.install('drawing')


def settle():
	"""Let frame callbacks and deferred tool previews finish."""
	loop = GLib.MainLoop()
	def finish():
		loop.quit()
		return GLib.SOURCE_REMOVE
	GLib.timeout_add(150, finish)
	loop.run()


class ApplicationSmokeTest(unittest.TestCase):
	def test_tool_switching_and_document_controls(self):
		with tempfile.TemporaryDirectory() as schema_dir:
			shutil.copy(source_dir.parent /
				'data/com.github.maoschanz.drawing.gschema.xml', schema_dir)
			subprocess.run(['glib-compile-schemas', schema_dir], check=True)
			os.environ['GSETTINGS_SCHEMA_DIR'] = schema_dir
			os.environ['GSETTINGS_BACKEND'] = 'memory'
			Gio.Resource.load(resource)._register()
			from drawing.main import Application
			from drawing.window import DrWindow
			from drawing.preferences import DrPrefsWindow
			from drawing.properties import DrPropertiesDialog
			from drawing.message_dialog import DrMessageDialog
			from drawing.canvas_input import CanvasInput

			Application.APP_ID = 'com.github.maoschanz.drawing.Test' + str(os.getpid())
			app = Application(os.environ.get('DRAWING_TEST_VERSION', '1.99.0-test'))
			settings = Gio.Settings.new('com.github.maoschanz.drawing')
			settings.set_strv('disabled-tools', [])
			settings.set_boolean('maximized', False)
			settings.set_int('default-width', 64)
			settings.set_int('default-height', 32)
			settings.set_strv('default-rgba', ['0.75', '0.5', '0.25', '1.0'])
			callback_errors = []
			with patch('sys.excepthook', lambda *error: callback_errors.append(error)):
				window = DrWindow(application=app)
				try:
					window.init_window_content_async({'gfile': None, 'get_cb': False})
					window.present()
					settle()
					self.assertGreaterEqual(set(window.tools), {
						'pencil', 'brush', 'eraser', 'highlight', 'text', 'points',
						'rect_select', 'free_select', 'line', 'arc', 'shape',
						'picker', 'color_select', 'paint', 'crop', 'scale',
						'rotate', 'skew', 'filters',
					})
					image = window.get_active_image()
					initial = image.get_initial_rgba()
					self.assertEqual((initial.red, initial.green, initial.blue,
						initial.alpha), (0.75, 0.5, 0.25, 1.0))
					before = bytes(image.surface.get_data())
					for tool_id, tool in window.tools.items():
						with self.subTest(tool=tool_id):
							tool.select_flowbox_child()
							settle()
							self.assertEqual(window.active_tool_id, tool_id)
							pane = window.options_manager.get_active_pane()
							self.assertTrue(pane.action_bar.get_mapped())
							for button in (pane.apply_btn, pane.cancel_btn):
								if button is not None:
									self.assertTrue(button.get_mapped())
									ok, bounds = button.compute_bounds(window)
									self.assertTrue(ok)
									self.assertGreaterEqual(bounds.get_x(), 0)
									self.assertLessEqual(bounds.get_x() + bounds.get_width(),
										window.get_width())
							self.assertEqual(bytes(image.surface.get_data()), before)
					for use_headerbar in (True, False):
						prefs = DrPrefsWindow(app.is_beta(), use_headerbar, application=app)
						try:
							prefs.present()
							settle()
							self.assertTrue(prefs.get_mapped())
						finally:
							prefs.destroy()
					properties = DrPropertiesDialog(window, image)
					try:
						properties.present()
						settle()
						self.assertEqual(properties.label_width.get_text(), '64 px')
						self.assertEqual(properties.label_height.get_text(), '32 px')
					finally:
						properties.destroy()
					# Keep document state intact when asynchronous close/save is
					# canceled or the selected destination cannot be written.
					window.tools['pencil'].select_flowbox_child()
					image._history._is_saved = False
					pixels = bytes(image.surface.get_data())
					closed = []
					window.request_close(closed.append)
					dialog = next(w for w in Gtk.Window.get_toplevels()
						if isinstance(w, DrMessageDialog) and w.get_visible())
					dialog.response(Gtk.ResponseType.DELETE_EVENT)
					self.assertEqual(closed, [False])
					self.assertTrue(window.get_visible())
					self.assertEqual(window.notebook.get_n_pages(), 1)
					manager = window.saving_manager
					# Mock only the external file chooser's result; perform the
					# production save continuation and real filesystem failure.
					for destination in (None, Gio.File.new_for_path(
						str(Path(schema_dir) / 'missing' / 'image.png'))):
						with self.subTest(destination=destination):
							result = []
							with patch.object(manager, '_file_chooser_save',
								side_effect=lambda image, callback: callback(destination)):
								manager.save_current_image(False, True, False, True,
									result.append, image)
							self.assertEqual(result, [False])
							self.assertIsNone(image.gfile)
							self.assertFalse(image.is_saved())
							self.assertEqual(bytes(image.surface.get_data()), pixels)
					# A queued self-save event cannot overwrite a newer edit.
					destination = Gio.File.new_for_path(str(Path(schema_dir) / 'saved.png'))
					result = []
					with patch.object(manager, '_file_chooser_save',
						side_effect=lambda image, callback: callback(destination)):
						manager.save_current_image(False, True, False, True,
							result.append, image)
					self.assertEqual(result, [True])
					self.assertTrue(image.is_saved())
					self.assertTrue(window.lookup_action('reload_file').get_enabled())
					original_file = image.gfile
					old_monitor = image._gfile_monitor
					result = []
					manager.save_current_image(False, False, False, True,
						result.append, image)
					self.assertEqual(result, [True])
					color = Gdk.RGBA()
					color.red = color.alpha = 1
					window.options_manager.set_left_color(color)
					before_edit = bytes(image.surface.get_data())
					event = CanvasInput(Gtk.GestureClick.new(),
						(10 - image.scroll_x) * image.zoom_level,
						(10 - image.scroll_y) * image.zoom_level, 1)
					image.on_press_on_area(image._drawing_area, event)
					image.on_release_on_area(image._drawing_area, event)
					pixels = bytes(image.surface.get_data())
					self.assertNotEqual(pixels, before_edit)
					image.reveal_reload_message(old_monitor, original_file, None,
						Gio.FileMonitorEvent.CHANGES_DONE_HINT)
					image.reveal_reload_message(image._gfile_monitor, image.gfile,
						None, Gio.FileMonitorEvent.CHANGES_DONE_HINT)
					self.assertEqual(bytes(image.surface.get_data()), pixels)
					self.assertFalse(image.is_saved())
					# Failed Save As keeps an existing file identity, not just None.
					bad = Path(schema_dir) / 'directory.png'
					bad.mkdir()
					result = []
					with patch.object(manager, '_file_chooser_save',
						side_effect=lambda image, callback: callback(Gio.File.new_for_path(str(bad)))):
						manager.save_current_image(False, True, False, True,
							result.append, image)
					self.assertEqual(result, [False])
					self.assertEqual(image.get_file_path(), original_file.get_path())
					self.assertEqual(bytes(image.surface.get_data()), pixels)
					self.assertFalse(image.is_saved())
					# External writes offer reload but never replace unsaved pixels.
					external = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True,
						8, 64, 32)
					external.fill(0x0000ffff)
					external.savev(original_file.get_path(), 'png', [], [])
					deadline = time.monotonic() + 5
					while not image.reload_info_bar.get_visible() and time.monotonic() < deadline:
						settle()
					self.assertTrue(image.reload_info_bar.get_visible())
					self.assertEqual(bytes(image.surface.get_data()), pixels)
					self.assertFalse(image.is_saved())
					image.reload_from_disk()
					self.assertEqual(bytes(image.main_pixbuf.get_pixels()),
						bytes(external.get_pixels()))
					self.assertTrue(image.is_saved())
					image.on_press_on_area(image._drawing_area, event)
					image.on_release_on_area(image._drawing_area, event)
					pixels = bytes(image.surface.get_data())
					exported = Path(schema_dir) / 'export.png'
					result = []
					with patch.object(manager, '_file_chooser_save',
						side_effect=lambda image, callback: callback(Gio.File.new_for_path(str(exported)))):
						manager.save_current_image(True, True, False, True,
							result.append, image)
					self.assertEqual(result, [True])
					self.assertTrue(exported.is_file())
					self.assertEqual(image.get_file_path(), original_file.get_path())
					self.assertEqual(bytes(image.surface.get_data()), pixels)
					self.assertFalse(image.is_saved())
					# Canceling alpha replacement never reports a completed save.
					cancelled = Path(schema_dir) / 'cancelled.jpg'
					result = []
					window.gsettings.set_string('replace-alpha', 'ask')
					with patch.object(manager, '_file_chooser_save',
						side_effect=lambda image, callback: callback(Gio.File.new_for_path(str(cancelled)))), \
					patch.object(manager, '_ask_overwrite_alpha',
						side_effect=lambda supported, can_save_as, callback: callback('cancel', None)):
						manager.save_current_image(False, True, False, True,
							result.append, image)
					self.assertEqual(result, [False])
					self.assertFalse(cancelled.exists())
					self.assertEqual(image.get_file_path(), original_file.get_path())
					self.assertEqual(bytes(image.surface.get_data()), pixels)
					self.assertFalse(image.is_saved())
					# Use the public clipboard path too: the GTK C convenience
					# setters are not all exposed by Python introspection.
					window.action_export_cb()
					window.build_image_from_clipboard()
					deadline = time.monotonic() + 5
					while window.notebook.get_n_pages() == 1 and time.monotonic() < deadline:
						settle()
					self.assertEqual(window.notebook.get_n_pages(), 2)
					self.assertEqual(bytes(window.get_active_image().surface.get_data()), pixels)
					# A failed replacement no longer belongs to the former file.
					window.notebook.set_current_page(window.notebook.page_num(image))
					old_monitor = image._gfile_monitor
					image.hide_reload_message()
					broken = Path(schema_dir) / 'broken.png'
					broken.write_bytes(b'not an image')
					image.try_load_file(Gio.File.new_for_path(str(broken)))
					image.reveal_reload_message(old_monitor, image.gfile, None,
						Gio.FileMonitorEvent.CHANGES_DONE_HINT)
					self.assertIsNone(image.get_file_path())
					self.assertIsNone(image._gfile_monitor)
					self.assertTrue(old_monitor.is_cancelled())
					self.assertFalse(image.reload_info_bar.get_visible())
					self.assertFalse(callback_errors, callback_errors)
				finally:
					window.destroy()
					app.quit()


if __name__ == '__main__':
	resource = sys.argv[1]
	# unittest parses its own options; retain the resource for the test.
	unittest.main(argv=[sys.argv[0]])
