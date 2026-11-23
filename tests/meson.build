test(
	'Contour tracing',
	python3,
	args: files('test_utilities_paths.py'),
	timeout: 30,
	env: ['PYTHONDONTWRITEBYTECODE=1'],
)

# This exercises production widgets and tool transitions, not screenshots or
# timing thresholds. Ordinary raster correctness stays in the headless oracle.
xvfb_run = find_program('xvfb-run', required: false)
dbus_run = find_program('dbus-run-session', required: false)
if xvfb_run.found() and dbus_run.found()
	test(
		'Selection bounds',
		xvfb_run,
		args: ['-a', dbus_run.full_path(), '--', python3.full_path(),
			files('test_selection_bounds.py')],
		timeout: 30,
		env: ['PYTHONDONTWRITEBYTECODE=1', 'GSETTINGS_BACKEND=memory',
			'GIO_USE_VFS=local', 'NO_AT_BRIDGE=1'],
	)
	test(
		'Application controls',
		xvfb_run,
		depends: drawing_resources,
		args: ['-a', dbus_run.full_path(), '--', python3.full_path(),
			files('test_gtk_application.py'),
			meson.project_build_root() / 'src/drawing.gresource'],
		timeout: 30,
		env: ['GSETTINGS_BACKEND=memory', 'PYTHONDONTWRITEBYTECODE=1',
			'GSK_RENDERER=cairo',
			'DRAWING_TEST_VERSION=' + meson.project_version()],
	)
else
	message('Application controls and selection bounds tests skipped: install xvfb and dbus')
endif

test(
	'Opaque image export',
	python3,
	args: files('test_opaque_export.py'),
	timeout: 30,
	env: ['PYTHONDONTWRITEBYTECODE=1'],
)

test(
	'Scale proportions',
	python3,
	args: files('test_scale_ratio.py'),
	timeout: 30,
	env: ['PYTHONDONTWRITEBYTECODE=1'],
)
