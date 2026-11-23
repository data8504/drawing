# Licensed under GPL3 https://github.com/maoschanz/drawing/blob/master/LICENSE

from gi.repository import Gdk, GLib
from .history_state import DrHistoryState


class DrHistoryManager():
	__gtype_name__ = 'DrHistoryManager'

	def __init__(self, image, **kwargs):
		self._image = image
		self._undo_history = []
		self._redo_history = []
		self._saved_revision = None
		self._waiting_for_rebuild = False
		self._replaying = False
		self._rebuilding = False

	def _current_revision(self):
		# Operations retain identity during replay; snapshots carry the
		# revision they cache, rather than becoming new document edits.
		state = self._undo_history[-1]
		return state.operations[-1] if state.operations else state.revision

	def get_saved(self):
		return not self._undo_history or \
			self._current_revision() is self._saved_revision

	def get_initial_operation(self):
		return self._undo_history[0].initial_state

	def empty_history(self):
		self._undo_history.clear()
		self._redo_history.clear()
		self._waiting_for_rebuild = False

	def try_undo(self):
		if self._operation_is_ongoing():
			self._image.active_tool().cancel_ongoing_operation()
			return
		while self._undo_history[-1].is_empty():
			if len(self._undo_history) == 1:
				return
			state = self._undo_history.pop()
			if not state.is_checkpoint:
				self._redo_history.append(state)
				break
		else:
			self._redo_history.append(self._undo_history[-1].pop_last_operation())
		self._rebuild_from_history_async()
		self._image.update_history_sensitivity()
		self._image.update_title()

	def try_redo(self, *args):
		self.finish_pending_rebuild()
		if not self._redo_history:
			return
		operation = self._redo_history.pop()
		self._replaying = True
		try:
			if isinstance(operation, DrHistoryState):
				self._undo_history.append(operation)
				self._image.restore_last_state()
			else:
				self._get_tool(operation['tool_id']).apply_operation(operation)
		finally:
			self._replaying = False
		self._image.update_history_sensitivity()
		self._image.update_title()

	def can_undo(self):
		return bool(self._undo_history) and (len(self._undo_history) > 1 or
			not self._undo_history[0].is_empty() or self._operation_is_ongoing())

	def can_redo(self):
		return bool(self._redo_history)

	def rewind_history(self):
		"""Reset to the initial image, retaining operations for redo."""
		operations = []
		for index, state in enumerate(self._undo_history):
			if index and not state.is_checkpoint:
				operations.append(DrHistoryState(state.initial_state,
					revision=state.revision))
			operations.extend(state.operations)
		self._redo_history = self._redo_history + operations[::-1]
		initial = self._undo_history[0]
		self._undo_history = [DrHistoryState(initial.initial_state,
			revision=initial.revision)]
		self._waiting_for_rebuild = False
		self._image.update_history_sensitivity()
		self._image.update_title()

	def add_operation(self, operation):
		self._image.set_surface_as_stable_pixbuf()
		if not self._replaying:
			self._redo_history.clear()
		self._undo_history[-1].add_operation(operation)
		if self._undo_history[-1].is_full() and not self._rebuilding \
		and not self._image.selection.is_active:
			# A plain pixbuf cannot restore an active selection. Wait until
			# deselection before caching, even beyond the normal bucket size.
			# This snapshot includes the operation just rendered. It is the
			# starting point for the NEXT bucket, never replayed with this one.
			self.add_state(self._image.main_pixbuf.copy(), is_checkpoint=True)
		self._image.update_title()

	def set_initial_operation(self, rgba_array, pixbuf, width, height):
		r, g, b, a = map(float, rgba_array)
		operation = {'tool_id': None, 'pixbuf': pixbuf,
			'rgba': Gdk.RGBA(red=r, green=g, blue=b, alpha=a),
			'width': width, 'height': height}
		# Reloads retain their preceding history and can be undone/redone.
		self._undo_history.append(DrHistoryState(operation))
		self._redo_history.clear()
		self._saved_revision = operation

	def add_state(self, pixbuf, is_checkpoint=False):
		if pixbuf is None:
			raise Exception(_("Attempt to save an invalid state"))
		revision = self._current_revision()
		operation = {'tool_id': None, 'pixbuf': pixbuf,
			'width': pixbuf.get_width(), 'height': pixbuf.get_height()}
		self._undo_history.append(DrHistoryState(operation,
			revision=revision, is_checkpoint=is_checkpoint))
		if not is_checkpoint:
			self._saved_revision = revision
		# Snapshot memory remains proportional to image size and edit count.
		# Eviction/merging and weighted operations require separate design.

	def has_initial_pixbuf(self):
		return self.get_initial_operation()['pixbuf'] is not None

	def get_last_stored_state(self):
		return self._undo_history[-1].initial_state

	def _rebuild_from_history_async(self):
		if not self._waiting_for_rebuild:
			self._waiting_for_rebuild = True
			GLib.timeout_add(500, self._rebuild_from_history, {})

	def finish_pending_rebuild(self):
		if self._waiting_for_rebuild:
			self._rebuild_from_history()

	def _rebuild_from_history(self, async_cb_data={}):
		if not self._waiting_for_rebuild:
			return False
		self._waiting_for_rebuild = False
		self._image.restore_last_state()
		operations = self._undo_history[-1].operations
		self._undo_history[-1].operations = []
		self._replaying = self._rebuilding = True
		try:
			for operation in operations:
				self._get_tool(operation['tool_id']).simple_apply_operation(operation)
		finally:
			self._replaying = self._rebuilding = False
		self._image.update()
		self._image.update_title()
		return False

	def _operation_is_ongoing(self):
		return self._image.active_tool().has_ongoing_operation()

	def _get_tool(self, tool_id):
		all_tools = self._image.window.tools
		if tool_id in all_tools:
			return all_tools[tool_id]
		self._image.window.reveal_action_report(_("Error: no tool '%s'" % tool_id))
