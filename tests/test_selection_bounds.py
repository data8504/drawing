#!/usr/bin/env python3

import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

import cairo
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, GdkPixbuf, GLib

source_dir = Path(__file__).resolve().parents[1] / 'src'
package = types.ModuleType('drawing')
package.__path__ = [str(source_dir)] + sorted({
	str(path.parent) for path in source_dir.rglob('*.py')
})
sys.modules['drawing'] = package
selection_module = importlib.import_module('drawing.selection_manager')
SelectionManager = selection_module.DrSelectionManager


def make_pixbuf(width, height):
	colors = []
	for y in range(height):
		for x in range(width):
			colors.extend((30 + x * 40, 40 + y * 60, 90 + x + y, 255))
	return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(bytes(colors)),
		GdkPixbuf.Colorspace.RGB, True, 8, width, height, width * 4)


def pixel(pixbuf, x, y):
	offset = y * pixbuf.get_rowstride() + x * pixbuf.get_n_channels()
	return tuple(pixbuf.get_pixels()[offset:offset + pixbuf.get_n_channels()])


def rectangle_path(x, y, width, height):
	surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
	context = cairo.Context(surface)
	context.rectangle(x, y, width, height)
	return context.copy_path()


class FakeImage:
	SCALE_FACTOR = 1
	scroll_x = 0
	scroll_y = 0

	def __init__(self, pixbuf):
		self.main_pixbuf = pixbuf
		self.action_updates = 0
		self.image_updates = 0

	def update_actions_state(self):
		self.action_updates += 1

	def update(self):
		self.image_updates += 1

	def is_zoomed_surface_sharp(self):
		return False


def make_manager(width=4, height=3):
	manager = SelectionManager.__new__(SelectionManager)
	manager.image = FakeImage(make_pixbuf(width, height))
	manager.init_pixbuf()
	manager.reset_future_data()
	return manager


class SelectionBoundsTest(unittest.TestCase):
	def test_top_left_padding_preserves_mapping_and_is_inert_when_moved(self):
		manager = make_manager()
		source_before = bytes(manager.image.main_pixbuf.get_pixels())
		manager.set_coords(True, -2, -1)
		path = rectangle_path(-2, -1, 5, 3)

		real_extract = Gdk.pixbuf_get_from_surface
		def checked_extract(surface, x, y, width, height):
			self.assertGreaterEqual(x, 0)
			self.assertGreaterEqual(y, 0)
			self.assertLessEqual(x + width, 4)
			self.assertLessEqual(y + height, 3)
			return real_extract(surface, x, y, width, height)

		with mock.patch.object(Gdk, 'pixbuf_get_from_surface',
		                       side_effect=checked_extract) as extract:
			manager.load_from_path(path)

		self.assertEqual(extract.call_count, 1)
		self.assertTrue(manager.is_active)
		self.assertEqual((manager.selection_x, manager.selection_y), (-2, -1))
		self.assertEqual((manager.selection_pixbuf.get_width(),
		                  manager.selection_pixbuf.get_height()), (5, 3))
		for y in range(3):
			for x in range(5):
				if x >= 2 and y >= 1:
					self.assertEqual(pixel(manager.selection_pixbuf, x, y),
					                 pixel(manager.image.main_pixbuf, x - 2, y - 1))
				else:
					self.assertEqual(pixel(manager.selection_pixbuf, x, y), (0, 0, 0, 0))

		output = cairo.ImageSurface(cairo.FORMAT_ARGB32, 8, 6)
		context = cairo.Context(output)
		context.set_source_rgb(0, 0, 1)
		context.paint()
		manager.show_selection_on_surface(context, False, 3, 2)
		moved = Gdk.pixbuf_get_from_surface(output, 0, 0, 8, 6)
		self.assertEqual(pixel(moved, 1, 1)[:3], (0, 0, 255))
		self.assertEqual(pixel(moved, 3, 2)[:3],
		                 pixel(manager.image.main_pixbuf, 0, 0)[:3])
		self.assertEqual(bytes(manager.image.main_pixbuf.get_pixels()), source_before)

	def test_fully_outside_selection_resets_without_extracting(self):
		for x, y in ((-8, -7), (8, -7), (-8, 7), (8, 7)):
			with self.subTest(x=x, y=y):
				manager = make_manager()
				manager.set_coords(True, x, y)
				with mock.patch.object(Gdk, 'pixbuf_get_from_surface') as extract:
					manager.load_from_path(rectangle_path(x, y, 2, 2))
				extract.assert_not_called()
				self.assertFalse(manager.is_active)
				self.assertIsNone(manager.selection_pixbuf)
				self.assertEqual((manager.selection_x, manager.selection_y), (0, 0))


if __name__ == '__main__':
	unittest.main()
