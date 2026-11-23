# message_dialog.py
#
# Copyright 2018-2023 Romain F. T.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from gi.repository import Gtk

class DrMessageDialog(Gtk.Window):
	"""A non-blocking message window that can also contain preview widgets."""
	__gtype_name__ = 'DrMessageDialog'

	def __init__(self, window, **kwargs):
		super().__init__(modal=True, transient_for=window,
		                 destroy_with_parent=True, **kwargs)
		self.set_default_size(350, -1)
		self._callback = None
		self._min_action_index = 0
		self.should_wrap = window.get_width() < 500
		self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
		for edge in ('top', 'bottom', 'start', 'end'):
			getattr(self._content, 'set_margin_' + edge)(12)
		self.set_child(self._content)
		self._message_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
		self._content.append(self._message_area)
		orientation = Gtk.Orientation.VERTICAL if self.should_wrap else Gtk.Orientation.HORIZONTAL
		self._actions = Gtk.Box(orientation=orientation, spacing=6, halign=Gtk.Align.END)
		self._content.append(self._actions)
		self.connect('close-request', self._on_close)
		shortcuts = Gtk.ShortcutController()
		shortcuts.add_shortcut(Gtk.Shortcut.new(
			Gtk.ShortcutTrigger.parse_string('Escape'),
			Gtk.CallbackAction.new(self._on_cancel)))
		self.add_controller(shortcuts)

	def set_action(self, label, style, is_default=False):
		self._min_action_index += 1
		response = self._min_action_index
		button = Gtk.Button(label=label)
		if style is not None:
			button.add_css_class(style)
		button.connect('clicked', lambda *_: self.response(response))
		self._actions.append(button)
		if is_default:
			self.set_default_widget(button)
		return response

	def add_string(self, string):
		self._message_area.append(Gtk.Label(label=string, wrap=self.should_wrap))

	def add_widget(self, widget):
		self._message_area.append(widget)

	def choose(self, callback):
		self._callback = callback
		self.present()

	def response(self, response):
		callback, self._callback = self._callback, None
		self.set_visible(False)
		try:
			if callback is not None:
				callback(response)
		finally:
			self.destroy()

	def _on_cancel(self, *args):
		self.response(Gtk.ResponseType.CANCEL)
		return True

	def _on_close(self, *args):
		self.response(Gtk.ResponseType.DELETE_EVENT)
		return True
