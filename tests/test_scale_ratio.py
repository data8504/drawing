#!/usr/bin/env python3

import gettext
import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

import gi

gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
source_dir = Path(__file__).resolve().parents[1] / 'src'
package = types.ModuleType('drawing')
package.__path__ = [str(source_dir)] + sorted({
	str(path.parent) for path in source_dir.rglob('*.py')
})
sys.modules['drawing'] = package
gettext.install('drawing')
scale = importlib.import_module('drawing.tool_scale')


class SpinButton:
	def __init__(self, value, callback):
		self.value = value
		self.callback = callback

	def get_value(self):
		return self.value

	def get_value_as_int(self):
		return int(self.value)

	def set_value(self, value):
		if value != self.value:
			self.value = value
			self.callback(self)


class ScaleRatioTest(unittest.TestCase):
	def setUp(self):
		self.tool = tool = scale.ToolScale.__new__(scale.ToolScale)
		tool._preserve_ratio = False
		tool._ratio_is_inverted = False
		tool._reload_is_locked = False
		tool._spinbtns_disabled = False
		tool.x_press = None
		tool._ratio = 2
		tool._spin_size = (100, 50)
		tool.get_option_value = lambda name: True
		tool._get_original_size = lambda: (100, 50)
		tool._width_btn = SpinButton(100, tool.on_spinbtn_changed)
		tool._height_btn = SpinButton(50, tool.on_spinbtn_changed)
		tool._w100_btn = SpinButton(100, tool.on_spinbtn100_changed)
		tool._h100_btn = SpinButton(100, tool.on_spinbtn100_changed)
		self.image = types.SimpleNamespace(temp_pixbuf=self.pixbuf(100, 50))
		tool.get_image = lambda: self.image
		tool.build_and_do_op = self.update_preview
		self.timers = []
		self.timer_patch = patch.object(scale.GLib, 'timeout_add',
			side_effect=lambda delay, callback, data:
				self.timers.append((callback, data)))
		self.timer_patch.start()
		self.addCleanup(self.timer_patch.stop)

	def pixbuf(self, width, height):
		return types.SimpleNamespace(get_width=lambda: width,
			get_height=lambda: height)

	def update_preview(self):
		self.image.temp_pixbuf = self.pixbuf(self.tool._get_width(),
			self.tool._get_height())

	def flush(self):
		while self.timers:
			callback, data = self.timers.pop(0)
			callback(data)

	def assert_size(self, width, height):
		self.flush()
		self.assertEqual((self.tool._get_width(), self.tool._get_height()),
			(width, height))

	def test_pixel_width_enters_locked_mode(self):
		self.tool._width_btn.set_value(200)
		self.assert_size(200, 100)

	def test_pixel_height_enters_locked_mode(self):
		self.tool._height_btn.set_value(100)
		self.assert_size(200, 100)

	def test_percentage_width_enters_locked_mode(self):
		self.tool._w100_btn.set_value(200)
		self.assert_size(200, 100)

	def test_percentage_height_enters_locked_mode(self):
		self.tool._h100_btn.set_value(200)
		self.assert_size(200, 100)

	def test_lock_uses_latest_unlocked_preview(self):
		self.tool.get_option_value = lambda name: False
		self.tool._height_btn.set_value(100)
		self.assert_size(100, 100)
		self.tool.get_option_value = lambda name: True
		self.tool._width_btn.set_value(200)
		self.assert_size(200, 200)

	def test_repeated_edits_before_delayed_refresh(self):
		self.tool._width_btn.set_value(200)
		self.tool._width_btn.set_value(300)
		self.assert_size(300, 150)

	def test_lock_after_queued_unlocked_edit_honors_the_latest_axis(self):
		self.tool.get_option_value = lambda name: False
		self.tool._width_btn.set_value(200)
		self.tool._width_btn.set_value(250)
		self.assertEqual(self.image.temp_pixbuf.get_width(), 200)
		self.tool.get_option_value = lambda name: True
		self.tool._height_btn.set_value(100)
		self.assert_size(500, 100)

	def test_change_locked_axis_before_delayed_refresh(self):
		self.tool._width_btn.set_value(200)
		self.tool._width_btn.set_value(300)
		self.tool._h100_btn.set_value(400)
		self.assert_size(400, 200)


if __name__ == '__main__':
	unittest.main()
