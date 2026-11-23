# Licensed under GPL3 https://github.com/maoschanz/drawing/blob/master/LICENSE

from gi.repository import Gdk, Gtk


class CanvasInput:
	"""Tool input sampled from a GTK controller in widget coordinates.

	Tools retain one input shape for mouse and tablet events; no Gdk event is
	kept past its controller callback.
	"""

	def __init__(self, controller, x=0, y=0, button=0, dx=0, dy=0):
		self.x = x
		self.y = y
		self.button = button
		self.delta_x = dx
		self.delta_y = dy
		self.state = controller.get_current_event_state()
		event = controller.get_current_event()
		self._device = event.get_device() if event else None
		self._tool = event.get_device_tool() if event else None
		self._pressure = None
		if isinstance(controller, Gtk.GestureStylus):
			ok, pressure = controller.get_axis(Gdk.AxisUse.PRESSURE)
			if ok:
				self._pressure = pressure

	def get_source_device(self):
		return self._device

	def get_device_tool(self):
		return self._tool

	def get_axis(self, axis):
		if axis == Gdk.AxisUse.PRESSURE:
			return self._pressure
		return None
