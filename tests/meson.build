test(
	'Contour tracing',
	python3.find_python(),
	args: files('test_utilities_paths.py'),
	timeout: 30,
	env: ['PYTHONDONTWRITEBYTECODE=1'],
)

gui_runner = find_program('xvfb-run', required: false)
private_bus = find_program('dbus-run-session', required: false)
if gui_runner.found() and private_bus.found()
	test(
		'Saved document state',
		gui_runner,
		args: ['-a', private_bus.path(), '--', python3.find_python().path(),
			files('test_save_state.py'),
			join_paths(meson.build_root(), 'src', 'drawing.gresource')],
		timeout: 30,
		depends: drawing_resources,
		env: ['PYTHONDONTWRITEBYTECODE=1', 'GSETTINGS_BACKEND=memory',
			'GIO_USE_VFS=local', 'NO_AT_BRIDGE=1'],
	)
else
	warning('GUI regression tests require xvfb-run and dbus-run-session')
endif
