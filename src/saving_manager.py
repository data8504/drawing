# saving_manager.py
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

from gi.repository import Gtk, Gdk, Gio, GdkPixbuf, GLib
from .message_dialog import DrMessageDialog
from .utilities_files import utilities_add_filechooser_filters
from .utilities_colors import utilities_rgb_to_hexadecimal

ALL_SUPPORTED_FORMAT = ['jpeg', 'jpg', 'jpe', 'png', 'tiff', 'ico', 'bmp']

################################################################################

class DrSavingManager():
	__gtype_name__ = 'DrSavingManager'

	def __init__(self, window):
		self._window = window

	def save_current_image(self, is_export, to_new, selection_only, allow_alpha,
	                       callback=None, image=None):
		"""Save one image, completing with True only after a successful write."""
		if getattr(self, '_saving', False):
			if callback is not None:
				callback(False)
			return
		self._saving = True
		image = image or self._window.get_active_image()

		def finished(success):
			self._saving = False
			if callback is not None:
				callback(success)

		def choose_file(confirmed):
			if not confirmed:
				finished(False)
			elif image.get_file_path() is None or to_new or is_export or selection_only:
				self._file_chooser_save(image, got_file)
			else:
				got_file(image.gfile)

		def got_file(gfile):
			if gfile is None:
				finished(False)
				return
			file_path = gfile.get_path()
			if file_path is None:
				self._window.reveal_message(_("Failed to save %s") % gfile.get_uri())
				finished(False)
				return
			file_format = self._get_format(file_path)
			pixbuf = image.selection.get_pixbuf() if selection_only else image.main_pixbuf

			def write(replacement=None):
				try:
					output = (self._replace_alpha(pixbuf, replacement, image)
			if replacement else pixbuf)
					output.savev(file_path, file_format, [], [])
					if not is_export:
						# Preserve the encoded representation, including JPEG and
						# flattened alpha, before completing the asynchronous save.
						image.reload_from_disk(gfile)
				except Exception as error:
					print(error)
					self._window.reveal_message(_("Failed to save %s") % file_path)
					finished(False)
					return
				finished(True)

			supports_alpha = file_format == 'png'
			if allow_alpha and supports_alpha:
				write()
				return
			replacement = self._window.gsettings.get_string('replace-alpha')
			if replacement != 'ask':
				write(replacement)
				return

			def alpha_chosen(action, replacement):
				if action == 'replace':
					write(replacement)
				elif action == 'save-as':
					self._file_chooser_save(image, got_file)
				else:
					finished(False)
			self._ask_overwrite_alpha(supports_alpha, allow_alpha and not is_export, alpha_chosen)

		if selection_only:
			choose_file(True)
		else:
			self._confirm_despite_ongoing_operation(choose_file)

	def confirm_save_modifs(self, callback, image=None):
		"""Ask whether an image may close, awaiting any requested save."""
		image = image or self._window.get_active_image()
		if image.is_saved():
			callback(True)
			return
		display_name = (image.get_filename_for_display()
			if image.get_file_path() else _("this picture"))
		dialog = DrMessageDialog(self._window)
		discard_id = dialog.set_action(_("Discard"), 'destructive-action')
		dialog.set_action(_("Cancel"), None)
		save_id = dialog.set_action(_("Save"), None, True)
		dialog.add_string(_("There are unsaved modifications to %s.") % display_name)
		preview = Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(image.main_pixbuf))
		preview.set_size_request(160, 100)
		dialog.add_widget(preview)

		def chosen(response):
			if response == save_id:
				self.save_current_image(False, False, False, True, callback, image)
			else:
				callback(response == discard_id)
		dialog.choose(chosen)

	def _confirm_despite_ongoing_operation(self, callback):
		message = None
		if self._window.get_selection_tool().selection_is_active():
			message = _("A part of the image is selected: the pixels beneath " +
			            "the selection will be saved with a color you might not expect!")
		elif self._window.active_tool().has_ongoing_operation():
			message = _("Modifications from the current tool haven't been applied.")
		if message is None:
			callback(True)
			return
		can_apply = self._window.lookup_action('apply_transform').get_enabled()
		can_unselect = (self._window.active_tool().apply_to_selection if can_apply
		                else self._window.lookup_action('unselect').get_enabled())
		dialog = DrMessageDialog(self._window)
		dialog.set_action(_("Cancel"), None, not (can_apply or can_unselect))
		apply_id = None
		if can_apply:
			apply_id = dialog.set_action(_("Apply & save"), 'suggested-action', True)
		elif can_unselect:
			apply_id = dialog.set_action(_("Deselect & save"), 'suggested-action', True)
		save_id = dialog.set_action(_("Save anyway"), None)
		dialog.add_string(message)
		dialog.add_string(_("Do you want to save anyway?"))

		def chosen(response):
			if response == apply_id:
				if can_apply:
					self._window.action_apply_transform()
				if can_unselect:
					self._window.action_unselect()
			callback(response in (apply_id, save_id))
		dialog.choose(chosen)

	def _file_chooser_save(self, image, callback):
		dialog = Gtk.FileDialog(title=_("Save picture as…"), modal=True)
		utilities_add_filechooser_filters(dialog)
		images_dir = GLib.get_user_special_dir(GLib.USER_DIRECTORY_PICTURES)
		if images_dir is not None:
			dialog.set_initial_folder(Gio.File.new_for_path(images_dir))
		dialog.set_initial_name(image.get_filename_for_display() if image.get_file_path()
		                        else _("Untitled") + '.png')

		def chosen(source, result):
			try:
				gfile = source.save_finish(result)
			except GLib.Error as error:
				if not error.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
					self._window.reveal_message(str(error))
				gfile = None
			callback(gfile)
		dialog.save(self._window, None, chosen)


	def _get_format(self, file_path):
		"""Build a short string which will be recognized as a file format by the
		GdkPixbuf.Pixbuf.savev method."""
		file_format = file_path.split('.')[-1]
		file_format = file_format.lower()
		if file_format in ['jpeg', 'jpg', 'jpe']:
			file_format = 'jpeg'
		elif file_format not in ALL_SUPPORTED_FORMAT:
			file_format = 'png'
		return file_format

	def _ask_overwrite_alpha(self, supports_alpha, can_save_as, callback):
		"""Warn the user about the replacement of the alpha channel for JPG or
		BMP files, but it may quickly annoy users to see a dialog so it's an
		option. Can be used on PNG files (if 'supports_alpha' is true)."""
		dialog = DrMessageDialog(self._window)
		cancel_id = dialog.set_action(_("Cancel"), None)
		if can_save_as:
			save_as_id = dialog.set_action(_("Save as…"), None)
		else:
			save_as_id = None
		# Context: confirm replacing transparent pixels with the selected color
		replace_id = dialog.set_action(_("Replace"), None, True)

		if not supports_alpha:
			dialog.add_string(_("This file format doesn't support transparent colors."))
		if can_save_as:
			dialog.add_string(_("You can save the image as a PNG file, or " \
			                                      "replace transparency with:"))
		else:
			dialog.add_string(_("Replace transparency with:"))

		alpha_combobox = Gtk.ComboBoxText(halign=Gtk.Align.CENTER)
		# Context: this is the label that describes the initial color of an
		# image (as set in the preferences or in the "new image with custom
		# size" dialog). This is displayed in the context of editing or saving
		# the image, but not when creating it.
		alpha_combobox.append('initial', _("Default color"))
		alpha_combobox.append('white', _("White"))
		alpha_combobox.append('black', _("Black"))
		# Context: replace transparent pixels with [checkboard]. This is a
		# pattern of dark and light greys.
		alpha_combobox.append('checkboard', _("Checkboard"))
		if not supports_alpha:
			# Context: replace transparent pixels with [nothing]. In practice it
			# means the alpha channel is just removed.
			alpha_combobox.append('nothing', _("Nothing"))
		alpha_combobox.set_active_id('initial') # If we run the dialog, it often
		# means the active preference is 'ask', so there is no way we can set
		# the default value to something more pertinent.
		dialog.add_widget(alpha_combobox)

		def chosen(response):
			if response == replace_id:
				callback('replace', alpha_combobox.get_active_id())
			elif response == save_as_id:
				callback('save-as', None)
			else:
				callback('cancel', None)
		dialog.choose(chosen)

	def _replace_alpha(self, pixbuf, replacement, image):
		if replacement == 'nothing':
			# wouldn't work with a PNG file
			return pixbuf
		width = pixbuf.get_width()
		height = pixbuf.get_height()
		if replacement == 'white':
			pcolor1 = utilities_rgb_to_hexadecimal(255, 255, 255)
			pcolor2 = utilities_rgb_to_hexadecimal(255, 255, 255)
		elif replacement == 'initial':
			initial_rgba = image.get_initial_rgba()
			r = int(initial_rgba.red * 255)
			g = int(initial_rgba.green * 255)
			b = int(initial_rgba.blue * 255)
			# the initial color has an alpha channel but it's not pertinent, and
			# not possible anyway.
			pcolor1 = utilities_rgb_to_hexadecimal(r, g, b)
			pcolor2 = utilities_rgb_to_hexadecimal(r, g, b)
		elif replacement == 'checkboard':
			pcolor1 = utilities_rgb_to_hexadecimal(85, 85, 85)
			pcolor2 = utilities_rgb_to_hexadecimal(170, 170, 170)
		else: # if replacement == 'black':
			pcolor1 = utilities_rgb_to_hexadecimal(0, 0, 0)
			pcolor2 = utilities_rgb_to_hexadecimal(0, 0, 0)
		# Flatten to RGB instead of retaining the source alpha channel.
		# At unchanged dimensions, nearest interpolation keeps opaque colors.
		result = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8,
		                            width, height)
		pixbuf.composite_color(result, 0, 0, width, height, 0, 0, 1, 1,
		                       GdkPixbuf.InterpType.NEAREST, 255,
		                       0, 0, 8, pcolor1, pcolor2)
		return result

	############################################################################
################################################################################
