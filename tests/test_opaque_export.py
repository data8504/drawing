#!/usr/bin/env python3

import importlib
from pathlib import Path
import sys
import tempfile
import types
import unittest

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
SavingManager = importlib.import_module('drawing.saving_manager').DrSavingManager


def pixbuf(colors, width=None, has_alpha=True):
	width = width or len(colors)
	channels = 4 if has_alpha else 3
	data = bytes(channel for color in colors for channel in color)
	return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(data),
		GdkPixbuf.Colorspace.RGB, has_alpha, 8, width, len(colors) // width,
		width * channels)


def pixel(image, x=0, y=0):
	offset = y * image.get_rowstride() + x * image.get_n_channels()
	return tuple(image.get_pixels()[offset:offset + image.get_n_channels()])


class OpaqueExportTest(unittest.TestCase):
	def setUp(self):
		self.manager = SavingManager(None)
		color = Gdk.RGBA()
		color.red, color.green, color.blue, color.alpha = .2, .4, .6, .3
		self.image = types.SimpleNamespace(get_initial_rgba=lambda: color)

	def flatten(self, source, replacement):
		result = self.manager._replace_alpha(source, replacement, self.image)
		self.assertFalse(result.get_has_alpha())
		self.assertEqual(result.get_n_channels(), 3)
		return result

	def test_opaque_endpoints_remain_exact(self):
		colors = [(255, 255, 255, 255), (255, 0, 0, 255),
			(0, 255, 0, 255), (0, 0, 255, 255), (0, 0, 0, 255)]
		for replacement in ('white', 'black', 'initial', 'checkboard'):
			with self.subTest(replacement=replacement):
				result = self.flatten(pixbuf(colors), replacement)
				for x, color in enumerate(colors):
					self.assertEqual(pixel(result, x), color[:3])

	def test_transparent_pixels_use_selected_background(self):
		source = pixbuf([(123, 45, 67, 0)])
		for replacement, expected in (('white', (255, 255, 255)),
		                            ('black', (0, 0, 0)),
		                            ('initial', (51, 102, 153))):
			with self.subTest(replacement=replacement):
				self.assertEqual(pixel(self.flatten(source, replacement)), expected)

	def test_checker_keeps_eight_pixel_squares(self):
		source = pixbuf([(12, 34, 56, 0)] * 16 * 16, width=16)
		result = self.flatten(source, 'checkboard')
		for x, y, level in ((0, 0, 85), (7, 7, 85), (8, 0, 170),
		                    (0, 8, 170), (8, 8, 85), (15, 15, 85)):
			self.assertEqual(pixel(result, x, y), (level, level, level))

	def test_rgb_source_colors_and_preserved_alpha_path(self):
		source = pixbuf([(255, 255, 255), (23, 91, 187)], has_alpha=False)
		result = self.flatten(source, 'white')
		self.assertEqual(pixel(result, 0), (255, 255, 255))
		self.assertEqual(pixel(result, 1), (23, 91, 187))
		source = pixbuf([(12, 34, 56, 78)])
		self.assertIs(self.manager._replace_alpha(source, 'nothing', self.image),
			source)
		self.assertEqual(pixel(source), (12, 34, 56, 78))

	def test_partial_alpha_composition(self):
		# GdkPixbuf's blend approximates rounded integer alpha in some cases.
		source = pixbuf([(229, 37, 119, 152)])
		for replacement, background in (('white', 255), ('black', 0)):
			result = pixel(self.flatten(source, replacement))
			for actual, channel in zip(result, (229, 37, 119)):
				expected = (channel * 152 + background * 103 + 127) // 255
				self.assertLessEqual(abs(actual - expected), 1)

	def test_core_formats_write_and_reopen(self):
		for format_name in ('png', 'jpeg', 'bmp'):
			for color in ((255, 255, 255), (23, 91, 187)):
				with self.subTest(format=format_name, color=color):
					with tempfile.TemporaryDirectory() as directory:
						source = pixbuf([(*color, 255)] * 15, width=5)
						result = self.flatten(source, 'white')
						path = str(Path(directory) / ('image.' + format_name))
						self.assertTrue(result.savev(path, format_name, [], []))
						loaded = GdkPixbuf.Pixbuf.new_from_file(path)
						self.assertEqual((loaded.get_width(), loaded.get_height()),
							(5, 3))
						for y in range(3):
							for x in range(5):
								for actual, expected in zip(pixel(loaded, x, y), color):
									if format_name == 'jpeg':
										self.assertLessEqual(abs(actual - expected), 2)
									else:
										self.assertEqual(actual, expected)


if __name__ == '__main__':
	unittest.main()
