#!/usr/bin/env python3

import gettext
import importlib
import os
from pathlib import Path
import sys
import types
import unittest

import gi

gi.require_version('Gdk', '3.0')
gi.require_version('Gtk', '3.0')
source_dir = Path(__file__).resolve().parents[1] / 'src'
package = types.ModuleType('drawing')
package.__path__ = [str(source_dir)] + sorted({
	str(path.parent) for path in source_dir.rglob('*.py')
})
sys.modules['drawing'] = package
gettext.install('drawing')
from gi.repository import Gio
Gio.Resource.load(os.environ['DRAWING_TEST_RESOURCE'])._register()
DrImage = importlib.import_module('drawing.image').DrImage


class CanvasCenteringTest(unittest.TestCase):
	def image(self, zoom):
		image = types.SimpleNamespace(zoom_level=zoom)
		for name in ('get_max_coord', '_get_centering_scroll', '_clamp_or_center'):
			setattr(image, name, types.MethodType(getattr(DrImage, name), image))
		return image

	def test_small_canvas_is_centered_at_each_zoom(self):
		for zoom in (.5, 1, 4):
			image = self.image(zoom)
			with self.subTest(zoom=zoom):
				self.assertEqual(image._clamp_or_center(0, 100, 100, 800),
					int((100 - 800 / zoom) / 2))

	def test_transform_preview_keeps_origin_across_widget_boundary(self):
		image = self.image(1)
		for preview in (100, 399, 400, 401, 800):
			with self.subTest(preview=preview):
				self.assertEqual(image._clamp_or_center(-150, preview, 100, 400),
					-150)

	def test_large_canvas_scroll_is_clamped(self):
		image = self.image(1)
		self.assertEqual(image._clamp_or_center(-10, 1000, 1000, 400), 0)
		self.assertEqual(image._clamp_or_center(700, 1000, 1000, 400), 600)
		self.assertEqual(image._clamp_or_center(50, 100, 1000, 400), 0)

	def test_centered_widget_coordinates_map_to_image(self):
		for zoom in (.5, 1, 4):
			image = self.image(zoom)
			image.scroll_x = image._clamp_or_center(0, 100, 100, 800)
			image.scroll_y = image._clamp_or_center(0, 50, 50, 600)
			for x, y in ((0, 0), (50, 25), (99, 49)):
				event = types.SimpleNamespace(x=(x - image.scroll_x) * zoom,
					y=(y - image.scroll_y) * zoom)
				self.assertEqual(DrImage.get_event_coords(image, event), (x, y))


if __name__ == '__main__':
	unittest.main()
