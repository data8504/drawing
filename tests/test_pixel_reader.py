#!/usr/bin/env python3

import importlib
from pathlib import Path
import sys
import types
import unittest

import cairo
import gi

gi.require_version('Gdk', '3.0')
gi.require_version('Gtk', '3.0')
from gi.repository import Gdk

source_dir = Path(__file__).resolve().parents[1] / 'src'
package = types.ModuleType('drawing')
package.__path__ = [str(source_dir)] + sorted({
	str(path.parent) for path in source_dir.rglob('*.py')
})
sys.modules['drawing'] = package
paths = importlib.import_module('drawing.utilities_paths')


class PixelReaderTest(unittest.TestCase):
	def assert_pixel(self, surface, x, y):
		expected = Gdk.pixbuf_get_from_surface(surface, x, y, 1, 1).get_pixels()
		self.assertEqual(paths.utilities_get_rgba_for_xy(surface, x, y), expected)

	def test_argb_channels_and_rounding(self):
		for alpha in (0, 1, 2, 3, 127, 128, 254, 255):
			for channel in (0, alpha // 2, alpha):
				with self.subTest(alpha=alpha, channel=channel):
					pixel = alpha << 24 | channel << 16 | (alpha // 2) << 8
					data = bytearray(pixel.to_bytes(4, sys.byteorder))
					surface = cairo.ImageSurface.create_for_data(data,
						cairo.FORMAT_ARGB32, 1, 1)
					self.assert_pixel(surface, 0, 0)

	def test_rgb24_ignores_padding_and_returns_three_channels(self):
		for padding in (0, 128, 255):
			pixel = padding << 24 | 0x123456
			data = bytearray(pixel.to_bytes(4, sys.byteorder))
			surface = cairo.ImageSurface.create_for_data(data,
				cairo.FORMAT_RGB24, 1, 1)
			self.assert_pixel(surface, 0, 0)
			self.assertEqual(paths.utilities_get_rgba_for_xy(surface, 0, 0),
				bytes((0x12, 0x34, 0x56)))

	def test_stride_flush_and_coordinates(self):
		data = bytearray(40)
		surface = cairo.ImageSurface.create_for_data(data,
			cairo.FORMAT_ARGB32, 3, 2, 20)
		context = cairo.Context(surface)
		context.set_source_rgba(.3, .5, .7, .5)
		context.paint()
		context.set_source_rgb(1, 0, 0)
		context.rectangle(2, 1, 1, 1)
		context.fill()
		for y in range(2):
			for x in range(3):
				self.assert_pixel(surface, x, y)
		self.assertEqual(paths.utilities_get_rgba_for_xy(surface, 2.9, 1.9),
			bytes((255, 0, 0, 255)))
		for point in ((-1, 0), (-.1, 0), (0, -.1), (3, 0), (0, 2)):
			with self.subTest(point=point):
				self.assertIsNone(paths.utilities_get_rgba_for_xy(surface, *point))


if __name__ == '__main__':
	unittest.main()
