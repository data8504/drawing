#!/usr/bin/env python3

import gettext
import importlib
from pathlib import Path
import sys
import types
import tempfile
import unittest
from unittest.mock import patch

import cairo
import gi

gi.require_version('Gdk', '3.0')
gi.require_version('Gtk', '3.0')
from gi.repository import Gdk, Gio, GdkPixbuf

source_dir = Path(__file__).resolve().parents[1] / 'src'
package = types.ModuleType('drawing')
package.__path__ = [str(source_dir)] + sorted({
	str(path.parent) for path in source_dir.rglob('*.py')
})
sys.modules['drawing'] = package
gettext.install('drawing')
history = importlib.import_module('drawing.history_manager')
AbstractTool = importlib.import_module(
	'drawing.abstract_tool').AbstractAbstractTool


class Image:
	def __init__(self):
		self.window = types.SimpleNamespace(tools={})
		self.selection = types.SimpleNamespace(is_active=False)
		self._history = history.DrHistoryManager(self)
		self.tool = Tool(self)
		self.window.tools['test'] = self.tool
		self._history.set_initial_operation((.3, .5, .7, .5), None, 80, 1)
		self.restore_last_state()

	def active_tool(self):
		return self.tool

	def restore_last_state(self):
		self.restore(self._history.get_last_stored_state())

	def restore(self, state):
		self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32,
			state['width'], state['height'])
		context = cairo.Context(self.surface)
		if state['pixbuf'] is None:
			rgba = state['rgba']
			context.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
		else:
			Gdk.cairo_set_source_pixbuf(context, state['pixbuf'], 0, 0)
		context.paint()
		self.set_surface_as_stable_pixbuf()

	def use_stable_pixbuf(self):
		self.restore({'width': self.main_pixbuf.get_width(),
			'height': self.main_pixbuf.get_height(), 'pixbuf': self.main_pixbuf})

	def set_surface_as_stable_pixbuf(self):
		self.main_pixbuf = Gdk.pixbuf_get_from_surface(self.surface, 0, 0,
			self.surface.get_width(), self.surface.get_height())

	def add_to_history(self, operation):
		self._history.add_operation(operation)

	def pixels(self):
		self.surface.flush()
		return bytes(self.surface.get_data())

	def update(self):
		pass

	update_title = update_actions_state = update_history_sensitivity = update


class Tool(AbstractTool):
	def __init__(self, image):
		self.image = image
		self.id = 'test'
		self._ongoing_operation = False

	def get_image(self):
		return self.image

	def restore_pixbuf(self):
		self.image.use_stable_pixbuf()

	def do_tool_operation(self, operation):
		self.start_tool_operation(operation)
		context = cairo.Context(self.image.surface)
		context.set_source_rgba(1, 0, 0, .5)
		context.rectangle(operation['x'], 0, 1, 1)
		context.fill()

	def show_error(self, message):
		raise AssertionError(message)

	def non_destructive_show_modif(self):
		pass


class HistoryTest(unittest.TestCase):
	def setUp(self):
		self.timer_patch = patch.object(history.GLib, 'timeout_add')
		self.timer_patch.start()
		self.addCleanup(self.timer_patch.stop)
		self.image = Image()
		self.manager = self.image._history

	def draw(self, x):
		self.image.tool.apply_operation({'tool_id': 'test', 'x': x})

	def undo(self):
		self.manager.try_undo()
		self.manager.finish_pending_rebuild()

	def test_pixels_undo_redo_across_checkpoints(self):
		states = [self.image.pixels()]
		for x in range(45):
			self.draw(x)
			states.append(self.image.pixels())
		for expected in reversed(states[:-1]):
			self.assertTrue(self.manager.can_undo())
			self.undo()
			self.assertEqual(self.image.pixels(), expected)
		self.assertFalse(self.manager.can_undo())
		for expected in states[1:]:
			self.manager.try_redo()
			self.assertEqual(self.image.pixels(), expected)
		self.assertFalse(self.manager.can_redo())

	def test_new_edit_finishes_pending_undo_and_discards_redo(self):
		for x in range(25):
			self.draw(x)
		self.manager.try_undo()
		self.assertTrue(self.manager._waiting_for_rebuild)
		self.draw(50)
		self.assertFalse(self.manager._waiting_for_rebuild)
		self.assertFalse(self.manager.can_redo())
		result = self.image.pixels()
		other = Image()
		for x in list(range(24)) + [50]:
			other.tool.apply_operation({'tool_id': 'test', 'x': x})
		self.assertEqual(result, other.pixels())

	def test_checkpoint_waits_for_selection_to_finish(self):
		self.image.selection.is_active = True
		for x in range(25):
			self.draw(x)
		self.assertEqual(len(self.manager._undo_history), 1)
		self.image.selection.is_active = False
		self.draw(26)
		self.assertEqual(len(self.manager._undo_history), 2)
		self.undo()
		self.assertEqual(len(self.manager._undo_history), 1)

	def test_initial_background_and_blank_replacement_survive_checkpoint(self):
		initial = self.manager.get_initial_operation()
		for x in range(25):
			self.draw(x)
		self.assertIs(self.manager.get_initial_operation(), initial)
		self.assertIn('rgba', self.manager.get_initial_operation())
		self.assertFalse(self.manager.has_initial_pixbuf())

	def test_saved_revision_survives_undo_and_redo(self):
		self.draw(1)
		self.manager.add_state(self.image.main_pixbuf.copy())
		self.assertTrue(self.manager.get_saved())
		self.draw(2)
		self.assertFalse(self.manager.get_saved())
		self.undo()
		self.assertTrue(self.manager.get_saved())
		self.undo() # Explicit save snapshot; same document revision.
		self.assertTrue(self.manager.get_saved())
		self.undo()
		self.assertFalse(self.manager.get_saved())
		self.manager.try_redo()
		self.assertTrue(self.manager.get_saved())
		self.manager.try_redo()
		self.manager.try_redo()
		self.assertFalse(self.manager.get_saved())

	def test_save_uses_pending_undo_result(self):
		self.draw(1)
		expected = self.image.main_pixbuf.get_pixels()
		self.draw(2)
		self.manager.try_undo()
		with tempfile.TemporaryDirectory() as directory:
			filename = str(Path(directory) / 'image.png')
			self.image.gfile = Gio.File.new_for_path(filename)
			self.image.get_file_path = lambda: filename
			self.image.pre_save = lambda gfile: None
			self.image.disable_monitoring = lambda: None
			window = types.SimpleNamespace(get_active_image=lambda: self.image)
			SavingManager = importlib.import_module(
				'drawing.saving_manager').DrSavingManager
			saving = SavingManager(window)
			saving._confirm_despite_ongoing_operation = lambda: True
			self.assertTrue(saving.save_current_image(False, False, False, True))
			loaded = GdkPixbuf.Pixbuf.new_from_file(filename)
			self.assertEqual(loaded.get_pixels(), expected)

	def reload(self):
		self.manager.set_initial_operation((0, 1, 0, 1), None, 60, 1)
		self.image.restore_last_state()

	def test_reload_is_reversible(self):
		self.draw(1)
		before = self.image.pixels()
		self.reload()
		after = self.image.pixels()
		self.assertTrue(self.manager.get_saved())
		self.undo()
		self.assertEqual(self.image.pixels(), before)
		self.assertFalse(self.manager.get_saved())
		self.manager.try_redo()
		self.assertEqual(self.image.pixels(), after)
		self.assertTrue(self.manager.get_saved())

	def test_reset_retains_operations_snapshots_and_existing_redo(self):
		initial = self.image.pixels()
		for x in range(45):
			self.draw(x)
		self.manager.add_state(self.image.main_pixbuf.copy())
		self.reload()
		self.draw(2)
		after = self.image.pixels()
		self.undo()
		self.image.restore(self.manager.get_initial_operation())
		self.manager.rewind_history()
		self.assertEqual(self.image.pixels(), initial)
		self.assertFalse(self.manager.can_undo())
		while self.manager.can_redo():
			self.manager.try_redo()
		self.assertEqual(self.image.pixels(), after)


if __name__ == '__main__':
	unittest.main()
