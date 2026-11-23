#!/usr/bin/env python3

import gettext
import importlib
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock

import cairo

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
paint = importlib.import_module('drawing.tool_paint')
select = importlib.import_module('drawing.select_color')


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

	def test_enlarged_preview_can_pan_after_preserving_origin(self):
		image = self.image(1)
		self.assertEqual(image._clamp_or_center(-150, 800, 100, 400), -150)
		self.assertEqual(image._clamp_or_center(-50, 800, 100, 400), -50)
		self.assertEqual(image._clamp_or_center(100, 800, 100, 400), 100)
		self.assertEqual(image._clamp_or_center(500, 800, 100, 400), 400)
		self.assertEqual(image._clamp_or_center(-200, 800, 100, 400), -150)
		image.scroll_x, image.scroll_y = 100, -175
		image.get_previewed_width = lambda: 800
		image.get_previewed_height = lambda: 50
		image.get_pixbuf_width = lambda: 100
		image.get_pixbuf_height = lambda: 50
		image.get_widget_width = image.get_widget_height = lambda: 400
		self.assertFalse(DrImage._scroll_needs_centering_fix(image))

	def test_negative_margins_do_not_paint_or_select(self):
		image = self.image(4)
		image.scroll_x = image.scroll_y = -100
		surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 8, 8)
		for x, y in ((-.1, 4), (-.5, 4), (-1, 4),
		             (4, -.1), (4, -.5), (4, -1)):
			with self.subTest(raw=(x, y)):
				event = types.SimpleNamespace(x=(x - image.scroll_x) * 4,
					y=(y - image.scroll_y) * 4)
				mapped = DrImage.get_event_coords(image, event)
				tool = paint.ToolPaint.__new__(paint.ToolPaint)
				tool._magic_path = None
				tool.get_option_value = Mock(return_value='replace')
				tool.build_operation = Mock()
				tool.apply_operation = Mock()
				tool.on_release_on_area(None, surface, *mapped)
				tool.apply_operation.assert_not_called()
				tool = select.ToolColorSelect.__new__(select.ToolColorSelect)
				tool._pre_load_path = Mock()
				tool.build_operation = Mock()
				tool.apply_operation = Mock()
				tool.release_define(surface, *mapped)
				tool.apply_operation.assert_not_called()

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
