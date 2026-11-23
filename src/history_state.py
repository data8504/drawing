# Licensed under GPL3 https://github.com/maoschanz/drawing/blob/master/LICENSE

class DrHistoryState():

	def __init__(self, stored_state, max_operations=20, revision=None,
	             is_checkpoint=False):

		# A saved state operation, containing a pixbuf, width, height...
		self.initial_state = stored_state
		self.revision = stored_state if revision is None else revision
		self.is_checkpoint = is_checkpoint

		# The next operations following self.initial state.
		# Cache after max_operations when the image has no active selection.
		self.operations = []

		self._max_operations = max_operations

	# Convenience methods.

	def pop_last_operation(self):
		return self.operations.pop() if len(self.operations) > 0 else None

	def add_operation(self, op):
		self.operations.append(op)

	def is_empty(self):
		return len(self.operations) == 0

	def is_full(self):
		return len(self.operations) >= self._max_operations
