# Licensed under GPL3 https://github.com/maoschanz/drawing/blob/master/LICENSE

from gi.repository import Gtk


def utilities_add_unit_to_spinbtn(spinbutton, width_chars, unit):
	spinbutton.set_width_chars(width_chars)
	spinbutton.set_max_width_chars(width_chars)
	if unit == 'px':
		# To translators: it's a measure unit, it appears in tooltips over
		# numerical inputs
		description = _("pixels")
	elif unit == '%':
		# To translators: it appears in tooltips over numerical inputs
		description = _("percents")
	elif unit == '°':
		# To translators: it's the angle measure unit, it appears in a tooltip
		# over a numerical input
		description = _("degrees")
	else:
		return
	# GTK4's SpinButton implements Editable rather than subclassing Entry.
	# Unit information belongs to the control, without entry-only icon slots.
	spinbutton.set_tooltip_text(description)
	spinbutton.update_property([Gtk.AccessibleProperty.DESCRIPTION], [description])
