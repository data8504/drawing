# Licensed under GPL3 https://github.com/maoschanz/drawing/blob/master/LICENSE

from contextlib import closing

from gi.repository import GdkPixbuf, Gio, GLib, Gtk

################################################################################

def utilities_add_filechooser_filters(dialog):
	"""Add file filters for images to file chooser dialogs."""
	allPictures = Gtk.FileFilter()
	allPictures.set_name(_("All pictures"))
	allPictures.add_mime_type('image/png')
	allPictures.add_mime_type('image/jpeg')
	allPictures.add_mime_type('image/bmp')
	allPictures.add_mime_type('image/svg+xml')

	pngPictures = Gtk.FileFilter()
	pngPictures.set_name(_("PNG images"))
	pngPictures.add_mime_type('image/png')

	jpegPictures = Gtk.FileFilter()
	jpegPictures.set_name(_("JPEG images"))
	jpegPictures.add_mime_type('image/jpeg')

	bmpPictures = Gtk.FileFilter()
	bmpPictures.set_name(_("BMP images"))
	bmpPictures.add_mime_type('image/bmp')

	svgPictures = Gtk.FileFilter()
	svgPictures.set_name(_("SVG images"))
	svgPictures.add_mime_type('image/svg+xml')

	filters = Gio.ListStore.new(Gtk.FileFilter)
	for file_filter in (allPictures, pngPictures, jpegPictures, bmpPictures, svgPictures):
		filters.append(file_filter)
	dialog.set_filters(filters)
	dialog.set_default_filter(allPictures)

################################################################################

def utilities_gfile_is_image(gfile, error_msg=""):
	try:
		infos = gfile.query_info('standard::type,standard::content-type,'
			'standard::fast-content-type', Gio.FileQueryInfoFlags.NONE, None)
		content_type = infos.get_attribute_string('standard::content-type')
		if content_type is None:
			content_type = infos.get_attribute_string('standard::fast-content-type')
		if content_type is None and infos.get_file_type() != Gio.FileType.DIRECTORY:
			basename = gfile.get_basename()
			if basename is not None:
				content_type, _uncertain = Gio.content_type_guess(basename, None)
		# The decoder still validates the actual image data.
		if content_type is not None and content_type.startswith('image/'):
			return True, error_msg
		error_msg += _("%s isn't an image.") % gfile.get_parse_name()
	except GLib.Error as error:
		error_msg += str(error)
	return False, error_msg

def utilities_load_pixbuf(gfile):
	path = gfile.get_path()
	if path is not None:
		return GdkPixbuf.Pixbuf.new_from_file(path)
	with closing(gfile.read(None)) as stream:
		return GdkPixbuf.Pixbuf.new_from_stream(stream, None)

def utilities_image_load_error(gfile, error):
	path = gfile.get_path()
	if path is not None:
		try:
			with open(path, 'rb') as file:
				header = file.read(12)
		except OSError:
			return str(error)
		if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
			message = _("Sorry, WEBP images can't be loaded by this app.") + " 😢 "
			if not path.endswith('.webp'):
				# Context: an error message, %s is a file path
				message += _("Despite its name, %s is a WEBP file.") % path
			return message
	return str(error)

################################################################################
