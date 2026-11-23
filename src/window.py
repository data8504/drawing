# window.py
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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# Import libs
import os
from gi.repository import Gtk, Gdk, Gio, GdkPixbuf, GLib

# Import various classes
from .image import DrImage
from .new_image_dialog import DrCustomImageDialog
from .minimap import DrMinimap
from .options_manager import DrOptionsManager
from .message_dialog import DrMessageDialog
from .deco_manager import DrDecoManagerMenubar, \
                          DrDecoManagerHeaderbar, \
                          DrDecoManagerToolbar
from .saving_manager import DrSavingManager
from .printing_manager import DrPrintingManager
from .tools_initializer import DrToolsInitializer

# Import various functions
from .utilities_files import utilities_add_filechooser_filters, \
                             utilities_gfile_is_image

UI_PATH = '/com/github/maoschanz/drawing/ui/'
DEFAULT_TOOL_ID = 'pencil'

################################################################################

@Gtk.Template(resource_path=UI_PATH+'window.ui')
class DrWindow(Gtk.ApplicationWindow):
	__gtype_name__ = 'DrWindow'

	gsettings = Gio.Settings.new('com.github.maoschanz.drawing')

	# Window empty widgets
	tools_flowbox = Gtk.Template.Child()
	toolbar_box = Gtk.Template.Child()
	info_bar = Gtk.Template.Child()
	info_label = Gtk.Template.Child()
	info_action = Gtk.Template.Child()
	notebook = Gtk.Template.Child()
	bottom_panes_box = Gtk.Template.Child()
	unfullscreen_btn = Gtk.Template.Child()
	bottom_meta_box = Gtk.Template.Child()
	tools_scrollable_box = Gtk.Template.Child()
	tools_nonscrollable_box = Gtk.Template.Child()

	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		self.app = kwargs['application']

		self.pointer_to_current_page = None # this ridiculous hack allows to
		                   # manage several tabs in a single window despite the
		                                      # notebook widget being pure shit
		self.active_tool_id = None
		self._is_tools_initialisation_finished = False
		self.devel_mode = False
		self.should_track_framerate = False

		self.set_default_size(self.gsettings.get_int("window-width"),
			self.gsettings.get_int("window-height"))
		if self.gsettings.get_boolean('maximized'):
			self.maximize()

		self._update_theme_variant()
		# self.resize(360, 648)
		# self.resize(720, 288)
		self._set_ui_bars()

	def init_window_content_async(self, content_params):
		"""Initialize the window's content, such as the minimap, the color
		popovers, the tools, their options, and a new image. Depending on the
		parameters, the new image can be imported from the clipboard, loaded
		from a GioFile, or (else) it can be a blank image.

		This method is called asynchronously, which isn't *correct* (not very
		thread-safe or anything) but it allows the window to be shown quicker.
		If it fails, a window is here anyway because this is independent from
		the object constructor."""

		self.reveal_action_report(_("Error starting the application, please" + \
		                                                   " report this bug."))

		gfile = content_params['gfile']
		get_cb = content_params['get_cb']

		self.tools = {}
		self.minimap = DrMinimap(self, None)
		self.options_manager = DrOptionsManager(self)
		self.saving_manager = DrSavingManager(self)
		self.printing_manager = DrPrintingManager(self)

		self.devel_mode = self.gsettings.get_boolean('devel-only')
		self.add_all_win_actions()
		self._init_tools()
		self.connect_signals()

		# The picture is built as late as possible in the init process because
		# reading files is too prone to exceptions that may fuck everything up,
		# and i don't trust that catching them is enough to ensure the process
		# can continue normally.
		try:
			if get_cb:
				# Initialize a placeholder while waiting for the clipboard.
				temporary = self._build_new_tab()
				GLib.timeout_add(500, self.async_build_from_clipboard, temporary)
			elif gfile is not None:
				self._build_new_tab(gfile=gfile)
			else:
				self.build_blank_image()
		except Exception as excp:
			self.reveal_message(str(excp))

		self.active_tool().select_flowbox_child()
		self._is_tools_initialisation_finished = True

		self._try_show_release_notes()

		# has to return False to be removed from the mainloop immediately
		return False

	def _try_show_release_notes(self):
		"""Add specific actions to the primary menu if the current version is a
		new one (the corresponding release notes have never been opened or
		dismissed)"""
		last_version = self.gsettings.get_string('last-version')
		current_version = self.app.get_current_version()
		if current_version == last_version:
			return

		self._decorations.set_release_notes_available(True)
		self.add_action_simple('help_news_dismiss', self._on_news_dismiss)
		self.add_action_simple('help_news_open', self._on_news_open)

	def _on_news_dismiss(self, *args):
		current_version = self.app.get_current_version()
		self.gsettings.set_string('last-version', current_version)
		self._decorations.set_release_notes_available(False)
		self.lookup_action('help_news_dismiss').set_enabled(False)
		self.lookup_action('help_news_open').set_enabled(False)

	def _on_news_open(self, *args):
		self.app.on_help_whats_new()
		self._on_news_dismiss()

	def _init_tools(self):
		"""Initialize all tools, building the UI for them including the menubar,
		and enable the default tool."""
		disabled_tools = self.gsettings.get_strv('disabled-tools')
		dev = self.gsettings.get_boolean('devel-only')
		self.tools = {}
		self.log_message('window has started, now loading tools')
		self._hide_message()

		tools_initializer = DrToolsInitializer(self)
		self.tools = tools_initializer.load_all_tools(dev, disabled_tools)

		# Side pane items for tools
		self.tools_flowbox.connect('selected-children-changed', \
		                           self._update_active_tool_from_flowbox_signal)
		for tool_id in self.tools:
			self.tools[tool_id].build_flowbox_child(self.tools_flowbox)
		self._update_show_labels()

		# Tools's menubar items if they don't exist yet (they're defined on the
		# application level, so they should only be built the first time)
		if not self.app.has_tools_in_menubar:
			self.build_menubar_tools_menu()

		# Initialisation of which tool is active
		tool_id = self.gsettings.get_string('last-active-tool')
		if tool_id not in self.tools:
			tool_id = DEFAULT_TOOL_ID
		self.active_tool_id = tool_id
		self.former_tool_id = tool_id
		# the end of this process will happen later because it requires an
		# active image, which doesn't exist at this point of the init process.

	def _update_active_tool_from_flowbox_signal(self, *args):
		selected_tool = self._get_newly_selected_tool()
		self.switch_to(selected_tool.id)

	def _get_newly_selected_tool(self):
		for tool_id in self.tools:
			if self.tools[tool_id].is_flowbox_child_selected():
				return self.tools[tool_id]

	def build_menubar_tools_menu(self):
		sections = [None, None, None]
		# the ids of the various kinds of tools don't match the index of their
		# section in the submenu
		sections[2] = self._get_menubar_tools_section(0)
		sections[0] = self._get_menubar_tools_section(1)
		sections[1] = self._get_menubar_tools_section(2)
		for tool_id in self.tools:
			tool = self.tools[tool_id]
			tool.add_item_to_menu(sections[tool.menu_id])
		self.app.has_tools_in_menubar = True

	def _get_menubar_tools_section(self, section_index):
		return self._get_menubar_item([
			[True, 4],
			[False, 1],
			[True, 0],
			[False, section_index]
		])

	############################################################################
	# TABS AND WINDOWS MANAGEMENT ##############################################

	def build_blank_image(self, *args):
		"""Open a new tab with a drawable blank image using the default values
		defined by user's settings."""
		width = self.gsettings.get_int('default-width')
		height = self.gsettings.get_int('default-height')
		rgba = self.gsettings.get_strv('default-rgba')
		self._build_new_tab(width=width, height=height, background_rgba=rgba)
		self.update_picture_title()

	def build_new_custom(self, *args):
		dialog = DrCustomImageDialog(self)
		def chosen(response):
			if response == dialog.create_id:
				width, height, rgba = dialog.get_values()
				self._build_new_tab(width=width, height=height, background_rgba=rgba)
				self.update_picture_title()
		dialog.choose(chosen)

	def async_build_from_clipboard(self, temporary):
		if self.get_application() is None or self.notebook.page_num(temporary) < 0:
			return GLib.SOURCE_REMOVE
		def created(has_image):
			if has_image:
				self.close_tab(temporary)
		self.build_image_from_clipboard(callback=created)
		return GLib.SOURCE_REMOVE

	def build_image_from_clipboard(self, *args, callback=None):
		def received(pixbuf):
			if pixbuf is not None:
				self._build_new_tab(pixbuf=pixbuf)
			else:
				self.reveal_message(_("The clipboard doesn't contain any image."), True)
				if self.notebook.get_n_pages() == 0:
					self.build_blank_image()
			if callback is not None:
				callback(pixbuf is not None)
		self._read_clipboard_image(received)

	def _read_clipboard_image(self, callback):
		clipboard = self.get_display().get_clipboard()
		def received(source, result):
			try:
				texture = source.read_texture_finish(result)
				pixbuf = Gdk.pixbuf_get_from_texture(texture) if texture is not None else None
			except GLib.Error:
				pixbuf = None
			if self.get_application() is not None:
				callback(pixbuf)
		clipboard.read_texture_async(None, received)

	def build_image_from_selection(self, *args):
		"""Open a new tab with the image in the selection."""
		pixbuf = self.get_active_image().selection.get_pixbuf()
		self._build_new_tab(pixbuf=pixbuf)

	def build_new_from_file(self, gfile, check_duplicates=True):
		if check_duplicates:
			window, duplicate = self.app.has_image_opened(gfile.get_path())
			if duplicate is not None:
				def confirmed(open_again):
					if open_again:
						self._build_new_tab(gfile=gfile)
					else:
						window.notebook.set_current_page(duplicate)
						window.present()
				self.confirm_open_twice(gfile, confirmed)
				return
		self._build_new_tab(gfile=gfile)

	def _build_new_tab(self, gfile=None, pixbuf=None, \
		                     width=200, height=200, \
		                     background_rgba=[0.5, 0.5, 0.5, 0.5]):
		"""Open a new tab with an optional file to load in it, or directly a
		pixbuf, or the color and dimensions of a blank tab."""

		new_image = DrImage(self)
		self.notebook.append_page(new_image, new_image.build_tab_widget())
		self.notebook.set_tab_reorderable(new_image, True)
		if gfile is not None:
			new_image.try_load_file(gfile)
		elif pixbuf is not None:
			new_image.try_load_pixbuf(pixbuf)
			# TODO dans l'idéal si on passe par les actions du clipboard, on
			# devrait n'ouvrir que si il n'y a pas de fenêtre, et ouvrir un truc
			# respectant les settings, plutôt qu'un petit pixbuf gris
		else:
			new_image.init_background(width, height, background_rgba)
		self._update_tabs_visibility()
		self.notebook.set_current_page(self.notebook.get_n_pages()-1)
		return new_image

	def confirm_open_twice(self, gfile, callback):
		dialog = DrMessageDialog(self)
		dialog.add_string(_("The file %s is already opened") % gfile.get_basename())
		open_again = dialog.set_action(_("Open again"), None)
		dialog.set_action(_("Switch to this image"), 'suggested-action', True)
		dialog.choose(lambda response: callback(response == open_again))

	def on_active_tab_changed(self, *args):
		if not self._is_tools_initialisation_finished:
			return
		self.switch_to(self.active_tool_id, args[1])
		# print("changement d'image")
		self.update_picture_title(args[1].update_title())
		self.minimap.set_zoom_label(args[1].zoom_level * 100)
		args[1].update_image_wide_actions()
		# On devrait être moins bourrin et conserver la sélection # TODO ?

	def update_tabs_menu_section(self, *args):
		action = self.lookup_action('active_tab')
		section = self._get_menubar_item([[True, 2], [False, 1]])
		section.remove_all()
		for page in [self.notebook.get_nth_page(i) for i in range(self.notebook.get_n_pages())]:
			tab_title = page.update_title()
			tab_index = self.notebook.page_num(page)
			section.append(tab_title, 'win.active_tab(' + str(tab_index) + ')')

	def action_tab_left(self, *args):
		# XXX (un)availability of this action
		current_page = self.notebook.get_current_page()
		if current_page == 0:
			self.notebook.set_current_page(self.notebook.get_n_pages() - 1)
		else:
			self.notebook.set_current_page(current_page - 1)

	def action_tab_right(self, *args):
		# XXX (un)availability of this action
		current_page = self.notebook.get_current_page()
		if current_page == self.notebook.get_n_pages() - 1:
			self.notebook.set_current_page(0)
		else:
			self.notebook.set_current_page(current_page + 1)

	def close_tab(self, tab, callback=None):
		"""Close this specific image after its asynchronous save decision."""
		index = self.notebook.page_num(tab)
		if index < 0:
			if callback is not None:
				callback(True)
			return
		if not tab.is_saved():
			self.notebook.set_current_page(index)
		def confirmed(can_close):
			if can_close:
				index = self.notebook.page_num(tab)
				if index >= 0:
					tab._cancel_gfile_monitoring()
					self.notebook.remove_page(index)
					tab.selection.reset(False)
					tab.main_pixbuf = tab.temp_pixbuf = None
					tab._history.empty_history()
					self._update_tabs_visibility()
			if callback is not None:
				callback(can_close)
		self.saving_manager.confirm_save_modifs(confirmed, tab)

	def action_close_tab(self, *args):
		if self.notebook.get_n_pages() > 1:
			self.get_active_image().try_close_tab()
		else:
			self.close()

	def action_close_window(self, *args):
		self.close()

	def on_close(self, *args):
		self.request_close()
		# GTK must leave the window alive while the user decides or saves.
		return True

	def request_close(self, callback=None):
		if (getattr(self, '_close_in_progress', False) or
			getattr(self.saving_manager, '_saving', False)):
			if callback is not None:
				callback(False)
			return
		self._close_in_progress = True
		def finished(success):
			self._close_in_progress = False
			if callback is not None:
				callback(success)
		def next_tab(success=True):
			if not success:
				finished(False)
				return
			if self.notebook.get_n_pages():
				self.close_tab(self.get_active_image(), next_tab)
				return
			if self._is_tools_initialisation_finished:
				self._decorations.remove_from_ui()
				self.options_manager.persist_tools_options()
				self.gsettings.set_string('last-active-tool', self.active_tool_id)
				self.gsettings.set_int('window-width', self.get_width())
				self.gsettings.set_int('window-height', self.get_height())
				self.gsettings.set_boolean('maximized', self.is_maximized())
			self.destroy()
			finished(True)
		next_tab()

	def connect_signals(self):
		# Closing the info bar
		self.info_bar.connect('close', self._hide_message)
		self.info_bar.connect('response', self._hide_message)

		# Closing the window
		self.connect('close-request', self.on_close)

		# Resizing the window
		self.connect('realize', self._connect_surface_layout)
		if self.get_realized():
			self._connect_surface_layout()

		# When a setting changes
		self.gsettings.connect('changed::deco-type', self.on_layout_changed)
		self.gsettings.connect('changed::big-icons', self.on_icon_size_changed)
		self.gsettings.connect('changed::direct-color-edit', \
		                                          self._update_use_color_editor)
		self.gsettings.connect('changed::preview-size', self.show_info_settings)
		self.gsettings.connect('changed::disabled-tools', self.show_info_settings)
		# Other settings are connected in DrImage.
		# Or when initializing the Gio.Actions

		# What happens when the active image change
		self.notebook.connect('switch-page', self.on_active_tab_changed)

		# Window key controller also exposes mnemonic hints while Alt is held.
		keys = Gtk.EventControllerKey.new()
		keys.connect('key-pressed', lambda controller, key, code, state:
			self._set_mnemonic_hints(key in (Gdk.KEY_Alt_L, Gdk.KEY_Alt_R)))
		keys.connect('key-released', lambda controller, key, code, state:
			self._set_mnemonic_hints(False))
		self.add_controller(keys)

		# Managing drag-and-drop
		if self.app.runs_in_sandbox:
			return # no dnd with actual file paths in the flatpak sandbox
			# XXX i could test if the app has home:ro permissions instead? eg to
			# help during development (where builder does have the permission)
		drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
		drop.connect('drop', self.on_data_dropped)
		self.notebook.add_controller(drop)


	def _get_menubar_item(self, path_description):
		"""Get an item of the app-wide menubar. The `path_description` object
		is an array of [boolean, int] couples. The boolean means if we're
		looking for a submenu, the int is an index."""
		current_item = self.app.get_menubar()
		for item in path_description:
			if item[0]:
				link_type = Gio.MENU_LINK_SUBMENU
			else:
				link_type = Gio.MENU_LINK_SECTION
			current_item = current_item.get_item_link(item[1], link_type)
		return current_item

	def add_action_simple(self, action_name, callback, shortcuts=[]):
		"""Convenient wrapper method adding a stateless action to the window. It
		will be named 'action_name' (string) and activating the action will
		trigger the method 'callback'."""
		action = Gio.SimpleAction.new(action_name, None)
		action.connect('activate', callback)
		self.add_action(action)
		self.app.set_accels_for_action('win.' + action_name, shortcuts)

	def add_action_boolean(self, action_name, default, callback):
		"""Convenient wrapper method adding a stateful action to the window. It
		will be named 'action_name' (string), be created with the state 'default'
		(boolean), and activating the action will trigger the method 'callback'."""
		action = Gio.SimpleAction().new_stateful(action_name, None, \
		                                      GLib.Variant.new_boolean(default))
		action.connect('change-state', callback)
		self.add_action(action)

	def add_action_persisted_boolean(self, gkey_name, callback, shortcuts = []):
		"""Convenient wrapper method adding a stateful action to the window, the
		action being linked to a GSettings key whose value is boolean. Both the
		key and the action will be named 'gkey_name' (string), and activating
		the action will trigger the method 'callback'."""
		action = self.gsettings.create_action(gkey_name)
		self.add_action(action)
		self.app.set_accels_for_action('win.' + gkey_name, shortcuts)
		self.gsettings.connect('changed::' + gkey_name, callback)

	def add_action_enum(self, action_name, default, callback):
		"""Convenient wrapper method adding a stateful action to the window. It
		will be named 'action_name' (string), be created with the state 'default'
		(string), and changing the active target of the action will trigger the
		method 'callback'."""
		action = Gio.SimpleAction().new_stateful(action_name, \
		            GLib.VariantType.new('s'), GLib.Variant.new_string(default))
		action.connect('change-state', callback)
		self.add_action(action)

	def add_all_win_actions(self):
		"""This doesn't add all window-wide GioActions, but only the GioActions
		which are here "by default", independently of any tool."""

		self.add_action_simple('main_menu', self.action_main_menu, ['F10'])
		self.add_action_simple('options_menu', self.action_options_menu, ['<Shift>F10'])

		action = Gio.PropertyAction.new('show-menubar', self, 'show-menubar')
		self.add_action(action)
		self.app.set_accels_for_action('win.show-menubar', ['<Ctrl>F2'])

		self.add_action_boolean('toggle_preview', False, self.action_toggle_preview)
		self.app.set_accels_for_action('win.toggle_preview', ['<Ctrl>m'])

		self.add_action_persisted_boolean('dark-theme-variant', \
		                                             self._update_theme_variant)
		self.add_action_persisted_boolean('show-labels', \
		                                       self._update_show_labels, ['F9'])

		self.add_action_boolean('hide_controls', False, self.action_hide_controls)
		self.app.set_accels_for_action('win.hide_controls', ['F8'])
		self.lookup_action('hide_controls').set_enabled(False)

		self.add_action_boolean('fullscreen', False, self.action_fullscreen)
		self.app.set_accels_for_action('win.fullscreen', ['F11'])

		self.add_action_simple('reset_canvas', self.action_reset, ['<Ctrl>BackSpace'])
		self.add_action_simple('reload_file', self.action_reload, ['<Ctrl>r'])
		self.add_action_simple('properties', self.action_properties)
		self.add_action_simple('unfullscreen', self.action_unfullscreen)

		self.add_action_simple('go_up', self.action_go_up, ['<Ctrl>Up'])
		self.add_action_simple('go_down', self.action_go_down, ['<Ctrl>Down'])
		self.add_action_simple('go_left', self.action_go_left, ['<Ctrl>Left'])
		self.add_action_simple('go_right', self.action_go_right, ['<Ctrl>Right'])

		self.add_action_simple('go_top', self.action_go_top, \
		                                  ['<Ctrl>Page_Up', '<Ctrl>KP_Page_Up'])
		self.add_action_simple('go_bottom', self.action_go_bottom, \
		                              ['<Ctrl>Page_Down', '<Ctrl>KP_Page_Down'])
		self.add_action_simple('go_first', self.action_go_first, \
		                                        ['<Ctrl>Home', '<Ctrl>KP_Home'])
		self.add_action_simple('go_last', self.action_go_last, \
		                                          ['<Ctrl>End', '<Ctrl>KP_End'])

		self.add_action_simple('zoom_in', self.action_zoom_in, \
		                                         ['<Ctrl>plus', '<Ctrl>KP_Add'])
		self.add_action_simple('zoom_out', self.action_zoom_out, \
		                                   ['<Ctrl>minus', '<Ctrl>KP_Subtract'])
		self.add_action_simple('zoom_100', self.action_zoom_100, ['<Ctrl>1', '<Ctrl>KP_1'])
		self.add_action_simple('zoom_opti', self.action_zoom_opti, ['<Ctrl>0', '<Ctrl>KP_0'])
		self.add_action_simple('zoom_max', self.action_zoom_max, ['<Ctrl><Shift>plus', '<Ctrl><Shift>KP_Add'])

		self.add_action_simple('new_tab', self.build_blank_image, ['<Ctrl>t'])
		self.add_action_simple('new_tab_custom', self.build_new_custom)
		self.add_action_simple('new_tab_selection', \
		                    self.build_image_from_selection, ['<Ctrl><Shift>t'])
		self.add_action_simple('new_tab_clipboard', \
		                    self.build_image_from_clipboard, ['<Ctrl><Shift>v'])
		self.add_action_simple('open', self.action_open, ['<Ctrl>o'])
		self.add_action_simple('tab_right', self.action_tab_right, ['<Ctrl>Tab'])
		self.add_action_simple('tab_left', self.action_tab_left, ['<Ctrl><Shift>Tab'])
		self.add_action_simple('close_tab', self.action_close_tab, ['<Ctrl>w'])
		self.add_action_simple('close', self.action_close_window)

		self.add_action_simple('undo', self.action_undo, ['<Ctrl>z'])
		self.add_action_simple('redo', self.action_redo, ['<Ctrl><Shift>z'])

		self.add_action_simple('save', self.action_save, ['<Ctrl>s'])
		self.add_action_simple('save_alphaless', self.action_save_alphaless)
		self.add_action_simple('save_as', self.action_save_as, ['<Ctrl><Shift>s'])
		self.add_action_simple('export_as', self.action_export_as)
		self.add_action_simple('to_clipboard', self.action_export_cb, ['<Ctrl><Shift>c'])
		self.add_action_simple('print', self.action_print, ['<Ctrl>p'])

		self.add_action_simple('import', self.action_import, ['<Ctrl>i'])
		self.add_action_simple('paste', self.action_paste, ['<Ctrl>v'])
		self.add_action_simple('select_all', self.action_select_all, ['<Ctrl>a'])
		self.add_action_simple('unselect', self.action_unselect, ['<Ctrl><Shift>a'])
		#self.add_action_simple('selection_invert', self.action_selection_invert)
		self.add_action_simple('selection_cut', self.action_cut, ['<Ctrl>x'])
		self.add_action_simple('selection_copy', self.action_copy, ['<Ctrl>c'])
		self.add_action_simple('selection_delete', self.action_delete, ['Delete'])

		self.add_action_simple('selection_export', self.action_selection_export)
		self.add_action_simple('selection-replace-canvas', \
		                                   self.action_selection_replace_canvas)
		self.add_action_simple('selection-expand-canvas', \
		                                    self.action_selection_expand_canvas)

		self.add_action_simple('back_to_previous', self.back_to_previous, ['<Ctrl>b'])
		self.add_action_simple('apply_transform', self.action_apply_transform, ['<Ctrl>Return'])
		self.add_action_simple('cancel_transform', self.action_cancel_transform)

		self.add_action_enum('active_tool', DEFAULT_TOOL_ID, self.on_change_active_tool)

		self.add_action_simple('main_color', self.action_color1, ['<Ctrl><Shift>l'])
		self.add_action_simple('secondary_color', self.action_color2, ['<Ctrl><Shift>r'])
		self.add_action_simple('exchange_color', self.exchange_colors, ['<Ctrl>e'])

		self.add_action_simple('size_more', self.action_size_more, ['<Ctrl><Shift>Up'])
		self.add_action_simple('size_less', self.action_size_less, ['<Ctrl><Shift>Down'])

		if self.devel_mode:
			self.add_action_simple('restore_pixbuf', self.action_restore)
			self.add_action_simple('rebuild_from_histo', self.action_rebuild)
			self.add_action_simple('get_values', self.action_getvalues, ['<Ctrl>g'])
			self.add_action_boolean('track_framerate', False, self.action_fsp)

		action = Gio.PropertyAction.new('active_tab', self.notebook, 'page')
		self.add_action(action)

	def set_cursor(self, is_custom):
		"""Called by the tools at various occasions, this method updates the
		mouse cursor according to `is_custom` (if False, use the default cursor)
		and the active tool `cursor_name` attribute."""
		if is_custom:
			name = self.active_tool().cursor_name
		else:
			name = 'default'
		try:
			self.set_cursor_from_name(name)
		except Exception as ex:
			# the cursor theme may be incorrect (not contain the cursor)
			self.reveal_message(str(ex))

	############################################################################
	# WINDOW DECORATIONS AND LAYOUTS ###########################################

	def on_layout_changed(self, *args):
		# GTK4 titlebars must be selected before realization. Existing windows
		# retain their layout; each new window reads the updated preference.
		if self.get_realized():
			self.show_info_settings()

	def show_info_settings(self, *args):
		"""This is executed when a setting changed but the method to apply it
		immediately in the current window doesn't exist."""
		self.reveal_message(_("Modifications will take effect in the next new window."))

	def update_picture_title(self, main_title=None):
		"""Set the window's title (regardless of the current UI bars), and the
		active tab title (indirectly)."""
		if main_title is None:
			main_title = self.get_active_image().update_title()
		self.update_tabs_menu_section()
		if self._decorations.set_title(main_title):
			self._decorations.force_update_titles()

	def set_window_subtitles(self, subtitles_list=None):
		"""Set the window's subtitles list (regardless of the current UI bars).
		Tools have to be initialized before calling this method, for now."""
		if subtitles_list is None:
			# TODO éviter ça en changeant les appels, et changer le commentaire
			subtitles_list = self.active_tool().get_editing_tips()
		if self._decorations.set_subtitles(subtitles_list):
			self._decorations.force_update_titles()

	def get_auto_decorations(self):
		"""Return the decorations setting based on the XDG_CURRENT_DESKTOP
		environment variable."""
		desktop_env = os.getenv('XDG_CURRENT_DESKTOP', 'GNOME')
		if 'GNOME' in desktop_env:
			return 'hg'
		elif 'Pantheon' in desktop_env:
			return 'he'
		elif 'Unity' in desktop_env:
			return 'tc'
		elif 'KDE' in desktop_env:
			return 'ts'
		elif 'Cinnamon' in desktop_env:
			return 'mts'
		elif desktop_env in ['MATE', 'XFCE', 'LXDE', 'LXQt']:
			return 'mtc'
		else:
			return 'hg' # Use the GNOME layout if the desktop is unknown,
		# because i don't know how the env variable is on mobile.

	def _set_ui_bars(self):
		"""Set the UI "bars" (headerbar, menubar, titlebar, toolbar, whatever)
		according to the user's preference, which by default is an empty string.
		In this case, an useful string is set by `get_auto_decorations()`."""
		self.has_good_width_limits = False

		# Remember the setting, so no need to restart this at each dialog.
		self.deco_layout = self.gsettings.get_string('deco-type')
		if self.deco_layout == '':
			self.deco_layout = self.get_auto_decorations()

		if self.deco_layout == 'hg':
			self._decorations = DrDecoManagerHeaderbar(False, self)
		elif self.deco_layout == 'he':
			self._decorations = DrDecoManagerHeaderbar(True, self)
		elif self.deco_layout == 'm':
			self._decorations = DrDecoManagerMenubar(self, True)
		elif 't' in self.deco_layout:
			symbolic = 's' in self.deco_layout
			menubar = 'm' in self.deco_layout
			self._decorations = DrDecoManagerToolbar(symbolic, menubar, self)
		else:
			self.gsettings.set_string('deco-type', '')
			self._set_ui_bars() # yes, recursion.

		if self.app.is_beta():
			self.add_css_class('devel')

	def action_main_menu(self, *args):
		self._decorations.toggle_menu()

	def action_options_menu(self, *args):
		"""This displays/hides the tool's options menu, and is implemented as an
		action to ease the accelerator (shift+f10)."""
		self.options_manager.toggle_menu()

	def _connect_surface_layout(self, *args):
		surface = self.get_surface()
		if surface is not getattr(self, '_layout_surface', None):
			self._layout_surface = surface
			surface.connect('layout', self._on_surface_layout)

	def _on_surface_layout(self, *args):
		if getattr(self, '_resize_pending', False):
			return
		self._resize_pending = True
		def allocated():
			self._resize_pending = False
			if self.get_realized() and self.notebook.get_n_pages():
				self._adapt_to_window_size()
			return GLib.SOURCE_REMOVE
		GLib.idle_add(allocated)

	def _adapt_to_window_size(self, *args):
		"""Adapts the headerbar (if any) and the default bottom pane to the new
		window size. If the current bottom pane isn't the default one, this
		will call the tool method applying the new size to the tool pane."""
		if not self.has_good_width_limits and self.get_allocated_width() > 700:
			self.options_manager.init_adaptability()
			self._decorations.init_adaptability()
			self.has_good_width_limits = True
		self._decorations.adapt_to_window_size()

		available_width = self.bottom_panes_box.get_allocated_width()
		if not self._is_tools_initialisation_finished:
			return # there is no active pane nor active image yet
		self.options_manager.adapt_to_window_size(available_width)

		# Check whether or not the scrollbars should now be displayed
		self.get_active_image().fake_scrollbar_update()

	def _update_tabs_visibility(self):
		controls_hidden = self.lookup_action('hide_controls').get_state()
		should_show = (self.notebook.get_n_pages() > 1) and not controls_hidden
		self.notebook.set_show_tabs(should_show)

	def action_dark_theme(self, *args):
		shall_be_dark = args[1]
		self.gsettings.set_boolean('dark-theme-variant', shall_be_dark)
		args[0].set_state(GLib.Variant.new_boolean(shall_be_dark))

	def _update_theme_variant(self, *args):
		key = 'gtk-application-prefer-dark-theme';
		use_dark_theme = self.gsettings.get_boolean('dark-theme-variant')
		Gtk.Settings.get_default().set_property(key, use_dark_theme)
		# XXX intriguant ce truc là ^ imho ça a changé, le night theme existe

	############################################################################
	# INFORMATION MESSAGES #####################################################

	def log_message(self, message):
		if self.devel_mode:
			print("Drawing: " + message)

	def reveal_action_report(self, message):
		"""Update the label and the visibility of the info bar. The 'report bug'
		action is suggested."""
		self.info_bar.set_visible(True)
		self.info_label.set_label(message)
		self.info_action.set_action_name('app.report-issue')
		self.info_action.set_label(_("Report a bug"))
		self.info_action.set_visible(True)
		self.log_message(message)

	def reveal_message(self, label, hide_afterwards=False):
		"""Update the label and the visibility of the info bar. No action is
		suggested, and the info bar may optionally be hidden after 4 seconds."""
		if hide_afterwards:
			GLib.timeout_add(4000, self.__hide_message_async, {'label': label})
		self.info_bar.set_visible(True)
		self.info_action.set_visible(False)
		self.info_label.set_label(label)
		self.log_message(label)

	def __hide_message_async(self, async_cb_data):
		"""This is used as a GSourceFunc so it should return False."""
		if async_cb_data['label'] == self.info_label.get_label():
			self._hide_message()
		# else the message has changed so it shouldn't be hidden now
		return False

	def _hide_message(self, *args):
		self.info_bar.set_visible(False)
		self.info_action.set_visible(False)
		self.info_label.set_label("")

	############################################################################
	# FULLSCREEN ###############################################################

	def action_unfullscreen(self, *args):
		"""Simple action, exiting fullscreen."""
		fs_action = self.lookup_action('fullscreen')
		fs_action.change_state(GLib.Variant.new_boolean(False))

	def action_fullscreen(self, *args):
		"""Boolean action, toggling fullscreen mode."""
		# XXX maybe track the window widget's 'window-state-event' to use this
		# https://lazka.github.io/pgi-docs/Gdk-3.0/flags.html#Gdk.WindowState.FULLSCREEN
		shall_fullscreen = args[1]
		if shall_fullscreen:
			self.fullscreen()
			self.reveal_message(_("Middle-click or press F8 to show/hide controls.") + \
			                     " " + _("Press F11 to exit fullscreen."), True)
			# TODO find a solution for touchscreens!!
		else:
			self.unfullscreen()
		self._set_controls_hidden(shall_fullscreen)
		self.lookup_action('hide_controls').set_enabled(shall_fullscreen)
		self.unfullscreen_btn.set_visible(shall_fullscreen)
		args[0].set_state(GLib.Variant.new_boolean(shall_fullscreen))

	def action_hide_controls(self, *args):
		"""Boolean action controlling the visibility of the UI elements such as
		the tools list, the bottom pane, the menubar/toolbar if any. This can
		only (in theory) be used while in fullscreen."""
		controls_hidden = args[1]
		self.tools_flowbox.set_visible(not controls_hidden)
		if 't' in self.deco_layout:
			self.toolbar_box.set_visible(not controls_hidden)
		if 'm' in self.deco_layout:
			self.set_show_menubar(not controls_hidden)
		self.bottom_meta_box.set_visible(not controls_hidden)
		args[0].set_state(GLib.Variant.new_boolean(controls_hidden))
		self._update_tabs_visibility()

	def _set_controls_hidden(self, state):
		hc_action = self.lookup_action('hide_controls')
		hc_action.change_state(GLib.Variant.new_boolean(state))

	def on_middle_click(self):
		is_fullscreened = self.lookup_action('fullscreen').get_state()
		if is_fullscreened:
			hc_action = self.lookup_action('hide_controls')
			self._set_controls_hidden(not hc_action.get_state())
		else:
			self.options_manager.get_active_pane().middle_click_action()

	############################################################################
	# SIDE PANE (TOOLS) ########################################################

	def on_icon_size_changed(self, *args):
		for tool_id in self.tools:
			self.tools[tool_id].update_icon_size()

	def set_tools_labels_visibility(self, visible):
		"""Change the way tools are displayed in the side pane. Visible labels
		mean the tools will be arranged in a scrollable list of buttons, else
		they will be in an adaptative flowbox."""
		for tool_id in self.tools:
			self.tools[tool_id].set_show_label(visible)
		nb_tools = len(self.tools)
		parent_box = self.tools_flowbox.get_parent()
		if visible:
			self.tools_flowbox.set_min_children_per_line(nb_tools)
			if parent_box == self.tools_nonscrollable_box:
				self.tools_nonscrollable_box.remove(self.tools_flowbox)
				self.tools_scrollable_box.append(self.tools_flowbox)
		else:
			if parent_box == self.tools_scrollable_box:
				self.tools_scrollable_box.remove(self.tools_flowbox)
				self.tools_nonscrollable_box.append(self.tools_flowbox)
			nb_min = int( (nb_tools+(nb_tools % 3))/3 ) - 1
			self.tools_flowbox.set_min_children_per_line(nb_min)
		self.tools_flowbox.set_max_children_per_line(nb_tools)

	def _update_show_labels(self, *args):
		self.set_tools_labels_visibility(self.gsettings.get_boolean('show-labels'))

	def _set_mnemonic_hints(self, visible):
		for tool in self.tools.values():
			tool.show_only_mnemonics(visible)
		return False

	############################################################################
	# TOOLS ####################################################################

	def on_change_active_tool(self, *args):
		"""Action callback, doing nothing in some situations, thus avoiding
		infinite loops. It sets the correct `tool_id` using adequate methods
		otherwise."""
		state_as_string = args[1].get_string()
		if state_as_string == args[0].get_state().get_string():
			return
		if self.tools[state_as_string].is_flowbox_child_selected():
			self.switch_to(state_as_string)
		else:
			self.tools[state_as_string].select_flowbox_child()

	def switch_to(self, new_tool_id, image_pointer=None):
		"""Switch from the current tool to `new_tool_id` and to the current
		image to `image_pointer` (`None` if the image is not changing)."""
		self.pointer_to_current_page = None

		action = self.lookup_action('active_tool')
		action.set_state(GLib.Variant.new_string(new_tool_id))

		# Disable the formerly active tool
		self.former_tool_id = self.active_tool_id
		should_preserve_selection = self.tools[new_tool_id].accept_selection
		self.former_tool().auto_apply(new_tool_id)
		self.former_tool().give_back_control(should_preserve_selection)
		self.former_tool().on_tool_unselected()
		self.get_active_image().selection.hide_popovers()

		self.pointer_to_current_page = image_pointer

		# Enable the newly selected tool
		self.get_active_image().update()
		self.active_tool_id = new_tool_id
		self.active_tool().on_tool_selected()
		self._update_bottom_pane()
		self.get_active_image().update_actions_state()
		self.on_tool_options_changed()

		self.pointer_to_current_page = None

	def _update_bottom_pane(self):
		"""Show the correct bottom pane, with the correct tool options menu."""
		try:
			self.options_manager.try_enable_pane(self.active_tool().pane_id)
			self.options_manager.update_pane(self.active_tool())
			self._build_options_menu()
			self._adapt_to_window_size()
		except Exception as e:
			self.reveal_message(_("Error loading the bottom pane for the " + \
			        "tool '%s', please report this bug.") % self.active_tool_id)
			print(e)

	def active_tool(self):
		return self.tools[self.active_tool_id]

	def former_tool(self):
		return self.tools[self.former_tool_id]

	def back_to_previous(self, *args):
		"""Switch back to the previously active tool, if it's different from the
		current one."""
		if self.former_tool_id == self.active_tool_id:
			self.force_selection()
			# avoid cases where applying a transform tool keeps the tool active
		else:
			self.tools[self.former_tool_id].select_flowbox_child()

	def _build_options_menu(self):
		"""Build the active tool's option menus.
		The first menu is the popover from the bottom bar. It can be built from
		a Gio.MenuModel, or it can contain any widget.
		The second menu is build from a Gio.MenuModel and is in the menubar (not
		available with all layouts)."""
		widget = self.active_tool().get_options_widget()
		model = self.active_tool().get_options_model()
		label = self.active_tool().get_options_label()
		if model is None:
			self.app.get_menubar().remove(5)
			item = Gio.MenuItem()
			item.set_label(label)
			item.set_action_and_target_value('win.PLACEHOLDER', None)
			self.app.get_menubar().insert_item(5, item)
		else:
			self.app.get_menubar().remove(5)
			self.app.get_menubar().insert_submenu(5, label, model)
		pane = self.options_manager.get_active_pane()
		pane.build_options_menu(widget, model, label)

	def on_tool_options_changed(self, *args):
		if self.active_tool_id is None:
			return
		self.active_tool().on_options_changed()
		self.set_window_subtitles()

	############################################################################
	# CLASSIC TOOLS PANE #######################################################

	def _update_use_color_editor(self, *args):
		use_editor = self.gsettings.get_boolean('direct-color-edit')
		self.options_manager.set_palette_setting(use_editor)

	def exchange_colors(self, *args):
		self.options_manager.get_classic_tools_pane().middle_click_action()
		self.active_tool().on_options_changed()

	def action_color1(self, *args):
		if self.active_tool().use_color:
			self.options_manager.left_color_btn().open()

	def action_color2(self, *args):
		if self.active_tool().use_color:
			self.options_manager.right_color_btn().open()

	def action_size_more(self, *args):
		self.options_manager.update_tool_width(1)

	def action_size_less(self, *args):
		self.options_manager.update_tool_width(-1)

	############################################################################
	# IMAGE FILES MANAGEMENT ###################################################

	def action_properties(self, *args):
		"""Display the properties dialog for the current image. This could be
		done here but it's done in DrImage to have a satisfying UML diagram."""
		self.get_active_image().show_properties()

	def action_fsp(self, *args):
		"""Development only: tracks and displays the framerate, thus it helps
		debugging how Gdk/cairo draws on the widget."""
		self.should_track_framerate = not self.should_track_framerate
		for img in [self.notebook.get_nth_page(i) for i in range(self.notebook.get_n_pages())]:
			img.reset_fps_counter()
		args[0].set_state(GLib.Variant.new_boolean(self.should_track_framerate))

	def get_active_image(self):
		if self.pointer_to_current_page is None:
			return self.notebook.get_nth_page(self.notebook.get_current_page())
		else:
			return self.pointer_to_current_page

	def action_reset(self, *args):
		self.get_active_image().reset_to_initial_pixbuf()

	def action_reload(self, *args):
		image = self.get_active_image()
		try:
			image.reload_from_disk()
		except GLib.Error:
			self.reveal_message(_("Failed to reload %s") % image.get_file_path())

	def action_open(self, *args):
		image = self.get_active_image()
		self.file_chooser_open(lambda gfile: self._open_chosen_file(image, gfile))

	def _open_chosen_file(self, image, gfile):
		def image_is_attached():
			return (image is not None and self.get_application() is not None
			        and self.notebook.page_num(image) >= 0)
		if gfile is None or not image_is_attached():
			return
		file_name = gfile.get_basename()
		self.reveal_message(_("Loading %s") % file_name)
		def choose_destination(open_again=True):
			if not image_is_attached():
				self._hide_message()
				return
			if not open_again:
				window, duplicate = self.app.has_image_opened(gfile.get_path())
				if duplicate is not None:
					window.notebook.set_current_page(duplicate)
					window.present()
				self._hide_message()
				return
			if image.should_replace():
				self._load_into_image(image, gfile)
				self._hide_message()
				return
			dialog = DrMessageDialog(self)
			new_tab = dialog.set_action(_("New Tab"), None, True)
			new_window = dialog.set_action(_("New Window"), None)
			discard = dialog.set_action(_("Discard changes"), 'destructive-action')
			if not image.is_saved():
				dialog.add_string(_("There are unsaved modifications to %s.") %
			image.get_filename_for_display())
			dialog.add_string(_("Where do you want to open %s?") % file_name)
			def chosen(response):
				if not image_is_attached():
					self._hide_message()
					return
				if response == new_tab:
					self.build_new_from_file(gfile, False)
				elif response == discard:
					self._load_into_image(image, gfile)
				elif response == new_window:
					self.app.open_window_with_content(gfile, False, False)
				self._hide_message()
			dialog.choose(chosen)
		window, duplicate = self.app.has_image_opened(gfile.get_path())
		if duplicate is not None:
			self.confirm_open_twice(gfile, choose_destination)
		else:
			choose_destination()

	def file_chooser_open(self, callback, title=None):
		dialog = Gtk.FileDialog(title=title or _("Open a picture"), modal=True)
		utilities_add_filechooser_filters(dialog)
		def chosen(source, result):
			try:
				gfile = source.open_finish(result)
			except GLib.Error as error:
				if not error.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
					self.reveal_message(str(error))
				gfile = None
			callback(gfile)
		dialog.open(self, None, chosen)

	def on_data_dropped(self, target, files, x, y):
		gfiles = []
		for gfile in files.get_files():
			is_image, error = utilities_gfile_is_image(gfile)
			if is_image:
				gfiles.append(gfile)
			else:
				self.reveal_message(error)
		if not gfiles:
			return False
		image = self.get_active_image()
		dialog = DrMessageDialog(self)
		dialog.set_action(_("Cancel"), None)
		open_id = dialog.set_action(_("Open"), None)
		import_id = dialog.set_action(_("Import"), None, True)
		label = gfiles[0].get_basename() if len(gfiles) == 1 else _("these files")
		dialog.add_string(_("What do you want to do with %s?") % label)
		def chosen(response):
			if response == open_id:
				for gfile in gfiles:
					self._build_new_tab(gfile=gfile)
			elif response == import_id:
				self.import_from_path(image, gfiles[0].get_path())
		dialog.choose(chosen)
		return True

	def _load_into_image(self, image, gfile):
		index = self.notebook.page_num(image)
		if index >= 0:
			self.notebook.set_current_page(index)
			image.try_load_file(gfile)
			self.update_picture_title()

	def has_image_opened(self, file_path):
		for tab in [self.notebook.get_nth_page(i) for i in range(self.notebook.get_n_pages())]:
			if tab.get_file_path() == file_path:
				return self.notebook.page_num(tab)
		return None

	def action_save(self, *args):
		"""Start saving the active image through asynchronous user decisions."""
		return self.saving_manager.save_current_image(False, False, False, True)

	def action_save_as(self, *args):
		return self.saving_manager.save_current_image(False, True, False, True)

	def action_save_alphaless(self, *args):
		return self.saving_manager.save_current_image(False, False, False, False)

	def action_export_as(self, *args):
		return self.saving_manager.save_current_image(True, True, False, True)

	def action_print(self, *args):
		pixbuf = self.get_active_image().main_pixbuf
		self.printing_manager.print_pixbuf(pixbuf)

	def action_export_cb(self, *args):
		self.get_display().get_clipboard().set(
			Gdk.Texture.new_for_pixbuf(self.get_active_image().main_pixbuf))
		self.reveal_message(_("Image copied to clipboard"), True)

	def action_getvalues(self, *args):
		"""Development only: helps debugging the selection."""
		self.get_active_image().selection.print_values()

	def action_select_all(self, *args):
		self.force_selection()
		self.get_selection_tool().select_all()

	def action_unselect(self, *args):
		self.get_selection_tool().give_back_control(False)

	def action_cut(self, *args):
		self.copy_operation()
		self.action_delete()

	def action_copy(self, *args):
		self.copy_operation()

	def copy_operation(self):
		self.get_display().get_clipboard().set(
			Gdk.Texture.new_for_pixbuf(self.get_active_image().selection.get_pixbuf()))

	def action_delete(self, *args):
		self.get_selection_tool().delete_selection()

	def action_paste(self, *args):
		image = self.get_active_image()
		def select_target():
			index = self.notebook.page_num(image)
			if index < 0:
				return False
			self.notebook.set_current_page(index)
			return True
		def text_received(source, result):
			try:
				text = source.read_text_finish(result)
			except GLib.Error:
				return
			if text is not None and select_target():
				self.tools['text'].force_text_tool(text)
		def image_received(pixbuf):
			if pixbuf is not None:
				if select_target():
					self.force_selection()
					self.get_selection_tool().import_selection(pixbuf)
			else:
				self.get_display().get_clipboard().read_text_async(None, text_received)
		self._read_clipboard_image(image_received)

	def action_import(self, *args):
		image = self.get_active_image()
		def chosen(gfile):
			if gfile is not None:
				self.import_from_path(image, gfile.get_path())
		self.file_chooser_open(chosen, _("Import a picture"))

	def import_from_path(self, image, file_path):
		"""Import a file as the selection pixbuf. Called by the 'win.import'
		action or when an image is imported by drag-and-drop."""
		if image is None or self.get_application() is None:
			return
		index = self.notebook.page_num(image)
		if index < 0:
			return
		pixbuf = GdkPixbuf.Pixbuf.new_from_file(file_path)
		self.notebook.set_current_page(index)
		self.force_selection()
		self.get_selection_tool().import_selection(pixbuf)

	def action_selection_export(self, *args):
		return self.saving_manager.save_current_image(True, True, True, True)

	def action_selection_replace_canvas(self, *args):
		self.get_selection_tool().replace_canvas()

	def action_selection_expand_canvas(self, *args):
		crop_tool = self.tools['crop']
		operation = crop_tool.build_selection_fit_operation()
		crop_tool.apply_operation(operation) # calling this here isn't elegant

	def action_selection_invert(self, *args):
		self.get_selection_tool().invert_selection()

	def get_selection_tool(self):
		if 'rect_select' in self.tools:
			return self.tools['rect_select']
		elif 'free_select' in self.tools:
			return self.tools['free_select']
		elif 'color_select' in self.tools:
			return self.tools['color_select']
		else:
			self.reveal_action_report(_("Required tool is not available"))
			return self.active_tool()

	def force_selection(self):
		self.get_selection_tool().select_flowbox_child()

	def action_apply_transform(self, *args):
		self.active_tool().on_apply_transform_tool_operation()

	def action_cancel_transform(self, *args):
		self.active_tool().on_cancel_transform_tool_operation()

	# Comportements des outils de transformation
	#
	# SI CANEVAS ENTIER :
	# *clic sur apply = apply, retour à l'outil précédent			OK
	# *clic sur annuler = cancel, retour à l'outil précédent		OK
	# *clic sur un autre outil = apply, passage à cet autre outil	OK
	#
	# SI SÉLECTION :
	# *clic sur apply = apply, retour à rect_select					OK
	# *clic sur annuler = cancel, retour à rect_select				OK
	# *clic sur un outil de sélection = apply, passage à l'outil	OK
	# *clic sur un autre outil = apply, passage à l'outil			OK

	############################################################################
	# HISTORY MANAGEMENT #######################################################

	def action_undo(self, *args):
		# self.reveal_message(_("Undoing…"))
		self.get_active_image().try_undo()
		# self.log_message('finished undoing')
		# self._hide_message()

	def action_redo(self, *args):
		self.get_active_image().try_redo()

	def action_restore(self, *args):
		"""[Dev only] show the last saved pixbuf on the canvas."""
		self.get_active_image().use_stable_pixbuf()
		self.get_active_image().update()

	def action_rebuild(self, *args):
		"""[Dev only] rebuild the image according to the history content."""
		self.get_active_image()._history._rebuild_from_history()

	def update_history_actions_labels(self, undo_label, redo_label):
		self._decorations.set_undo_label(undo_label)
		self._decorations.set_redo_label(redo_label)

	############################################################################
	# PREVIEW, NAVIGATION AND ZOOM ACTIONS #####################################

	def action_go_up(self, *args):
		self.get_active_image().add_deltas(0, -1, 100)

	def action_go_down(self, *args):
		self.get_active_image().add_deltas(0, 1, 100)

	def action_go_left(self, *args):
		self.get_active_image().add_deltas(-1, 0, 100)

	def action_go_right(self, *args):
		self.get_active_image().add_deltas(1, 0, 100)

	def action_go_top(self, *args):
		self.get_active_image().reset_deltas(0, -1)

	def action_go_bottom(self, *args):
		self.get_active_image().reset_deltas(0, 1)

	def action_go_first(self, *args):
		self.get_active_image().reset_deltas(-1, 0)

	def action_go_last(self, *args):
		self.get_active_image().reset_deltas(1, 0)

	def action_toggle_preview(self, *args):
		"""Action callback, showing or hiding the "minimap" preview popover."""
		preview_visible = not args[0].get_state()
		if preview_visible:
			self.minimap.popup()
			self.minimap.update_content()
		else:
			self.minimap.popdown()
		args[0].set_state(GLib.Variant.new_boolean(preview_visible))

	def action_zoom_in(self, *args):
		self.get_active_image().inc_zoom_level(25)

	def action_zoom_out(self, *args):
		self.get_active_image().inc_zoom_level(-25)

	def action_zoom_100(self, *args):
		self.get_active_image().set_zoom_level(100)

	def action_zoom_opti(self, *args):
		self.get_active_image().set_opti_zoom_level()

	def action_zoom_max(self, *args):
		self.get_active_image().set_zoom_level(2000)
		# It has to be done twice, because the code of the minimap is shit
		self.get_active_image().set_zoom_level(2000)

	############################################################################
################################################################################

