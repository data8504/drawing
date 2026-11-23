
project(
	'drawing',
	version: '1.2.1',
	meson_version: '>= 0.56',
)
app_uuid = 'com.github.maoschanz.drawing'

# Dependencies #################################################################

python3 = import('python').find_installation('python3', modules: ['gi', 'cairo'])
run_command(python3, '-c',
    'import gi; gi.require_version("Gtk", "4.0"); gi.require_foreign("cairo"); from gi.repository import Gtk; error = Gtk.check_version(4, 10, 0); assert error is None, error',
    check: true,
)

################################################################################

# Will be used in po and data
if get_option('enable-translations-and-appdata')
	i18n = import('i18n')
endif

# Will be used in help and src
gnome = import('gnome')

subdir('data')
subdir('src')
subdir('po')
subdir('help')
subdir('tests')

meson.add_install_script('build-aux/meson/postinstall.py')

################################################################################
