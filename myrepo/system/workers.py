import logging
import os
import shlex
import sys
import time
from typing import Callable, Dict, List, Any, Optional, Union, Iterator, cast

if sys.platform == 'linux':
	from select import epoll as epoll
	from select import EPOLLIN as EPOLLIN
	from select import EPOLLHUP as EPOLLHUP
else:
	import select
	EPOLLIN = 0
	EPOLLHUP = 0

	class epoll():
		""" #!if windows
		Create a epoll() implementation that simulates the epoll() behavior.
		This creates one interface for epoll() across all platforms by wrapping select() when epoll() is not available.
		"""
		def __init__(self) -> None:
			self.sockets: Dict[str, Any] = {}
			self.monitoring: Dict[int, Any] = {}

		def unregister(self, fileno :int, *args :List[Any], **kwargs :Dict[str, Any]) -> None:
			try:
				del(self.monitoring[fileno])
			except: # nosec
				pass

		def register(self, fileno :int, *args :int, **kwargs :Dict[str, Any]) -> None:
			self.monitoring[fileno] = True

		def poll(self, timeout: float = 0.05, *args :str, **kwargs :Dict[str, Any]) -> List[Any]:
			try:
				return [[fileno, 1] for fileno in select.select(list(self.monitoring.keys()), [], [], timeout)[0]]
			except OSError:
				return []

from ..exceptions import SysCallError
from ..environment.storage import storage
from .logger import log
from .helpers import locate_binary, pid_exists, clear_vt100_escape_codes

class SysCommandWorker:
	def __init__(self,
		cmd :Union[str, List[str]],
		callbacks :Optional[Dict[str, Any]] = None,
		peak_output :Optional[bool] = False,
		environment_vars :Optional[Dict[str, Any]] = None,
		logfile :Optional[None] = None,
		working_directory :Optional[str] = './',
		remove_vt100_escape_codes_from_lines :bool = True):
		"""
		A general purpose system-command class which can execute and communicate
		with a spawned process. It also supports communicating with sub-tty's which
		for instance SSH uses to get user passwords.
		This class requires the user of it to poll periodicly for output, otherwise
		the process will hang/freeze. For a more convenient method of
		calling system-commands, use the class :ref:`SysCommand` instead.
		"""

		if not callbacks:
			callbacks = {}
		if not environment_vars:
			environment_vars = {}

		if type(cmd) is str:
			cmd = shlex.split(cmd)

		cmd = list(cmd) # This is to please mypy
		if cmd[0][0] != '/' and cmd[0][:2] != './':
			# "which" doesn't work as it's a builtin to bash.
			# It used to work, but for whatever reason it doesn't anymore.
			# We there for fall back on manual lookup in os.PATH
			cmd[0] = locate_binary(cmd[0])

		self.cmd = cmd
		self.callbacks = callbacks
		self.peak_output = peak_output
		self.environment_vars = environment_vars
		self.logfile = logfile
		self.working_directory = working_directory

		self.exit_code :Optional[int] = None
		self._trace_log :bytes = b''
		self._trace_log_pos = 0
		self.poll_object = epoll()
		self.child_fd :Optional[int] = None
		self.started :Optional[float] = None
		self.ended :Optional[float] = None
		self.remove_vt100_escape_codes_from_lines :bool = remove_vt100_escape_codes_from_lines

	def __contains__(self, key: bytes) -> bool:
		"""
		Contains will also move the current buffert position forward.
		This is to avoid re-checking the same data when looking for output.
		Contains allows us to do ``b"some string" in SysCommandWorker("...")``.
		"""
		if type(key) != bytes:
			raise AssertionError(f"SysCommand* requires comparison key to be bytes() when doing `x in SysCommand*('...')`")

		if (contains := key in self._trace_log[self._trace_log_pos:]):
			self._trace_log_pos += self._trace_log[self._trace_log_pos:].find(key) + len(key)

		return contains

	def __iter__(self, *args :str, **kwargs :Dict[str, Any]) -> Iterator[bytes]:
		"""
		Iterates over the current lines in the trace buffert.
		This will move the buffert position forward.
		"""
		for line in self._trace_log[self._trace_log_pos:self._trace_log.rfind(b'\n')].split(b'\n'):
			if line:
				if self.remove_vt100_escape_codes_from_lines:
					line = clear_vt100_escape_codes(line)

				yield line + b'\n'

		self._trace_log_pos = self._trace_log.rfind(b'\n')

	def __repr__(self) -> str:
		"""
		Returns a string representation of the trace log.
		"""
		self.make_sure_we_are_executing()
		return str(self._trace_log)

	def __enter__(self) -> 'SysCommandWorker':
		"""
		Returns an instance of SysCommandWorker to use with context managers.
		"""
		return self

	def __exit__(self, *args :str) -> None:
		"""
		Upon exit, SysCommandWorker() will attempt to close any remaining pipes.
		It will also clear the output if ``peak_output=True``.
		Any errors within the context manager will also be logged.

		If the spawned process exited in a abnormal way, meaning ``exit_code != 0``
		that will be caught and a ``SysCallError`` will be raised.
		"""

		if self.child_fd:
			try:
				os.close(self.child_fd)
			except: # nosec
				print('Exception!')
				pass

		if self.peak_output:
			# To make sure any peaked output didn't leave us hanging
			# on the same line we were on.
			sys.stdout.write("\n")
			sys.stdout.flush()

		if len(args) >= 2 and args[1]:
			log(args[1], level=logging.ERROR, fg='red')

		if self.exit_code != 0:
			raise SysCallError(f"{self.cmd} exited with abnormal exit code [{self.exit_code}]: {self.decode()[:100]}", self.exit_code)

	def is_alive(self) -> bool:
		"""
		Returns ``True`` if the process is still active. False otherwise.
		"""
		self.poll()

		if self.started and self.ended is None:
			return True

		return False

	def write(self, data: bytes, line_ending :bool = True) -> int:
		"""
		Writes bytes data to the spawned process using `os.write` to the childs file descriptor.
		"""
		if type(data) != bytes:
			raise AssertionError(f"SysCommand*.write() requires bytes-data and not {type(data)}")

		self.make_sure_we_are_executing()

		if self.child_fd:
			return os.write(self.child_fd, data + (b'\n' if line_ending else b''))

		return 0

	def make_sure_we_are_executing(self) -> bool:
		"""
		Ensures that the process has been spawned.
		Can be called multiple times without spawning copies of the process.
		"""
		if not self.started:
			return self.execute()
		return True

	def tell(self) -> int:
		"""
		Returns which position we have in the trace-log.
		Much like ``.tell()`` on any file handle in Python.
		"""
		self.make_sure_we_are_executing()
		return self._trace_log_pos

	def seek(self, pos :int) -> None:
		"""
		Moves the trace-log cursor to the given position.
		Much like ``.seek()`` on any file handle in Python.
		"""
		self.make_sure_we_are_executing()
		# Safety check to ensure 0 < pos < len(tracelog)
		self._trace_log_pos = min(max(0, pos), len(self._trace_log))

	def peak(self, output: Union[str, bytes]) -> bool:
		"""
		``peak()`` is a wrapper for ``sys.stdout.write`` but will only
		output data if ``.peak_output`` was set on ``SysCommandWorker()``
		"""
		if self.peak_output:
			if type(output) == bytes:
				try:
					output = output.decode('UTF-8')
				except UnicodeDecodeError:
					return False

			sys.stdout.write(str(output))
			sys.stdout.flush()

		return True

	def poll(self) -> bool:
		"""
		This function will return ``True`` if there was data retrieved.
		It will also do some health checks on the process and if it ended,
		this function will set a ```time of death`` for the process and a ``.exit_code``.
		"""
		self.make_sure_we_are_executing()

		got_output = False
		if self.child_fd:
			for fileno, event in self.poll_object.poll(0.1):
				try:
					output = os.read(self.child_fd, 8192)
					got_output = True
					self.peak(output)
					self._trace_log += output
				except OSError:
					self.ended = time.time()
					break

			if self.ended or (got_output is False and pid_exists(self.pid) is False):
				self.ended = time.time()
				try:
					self.exit_code = os.waitpid(self.pid, 0)[1]
				except ChildProcessError:
					try:
						self.exit_code = os.waitpid(self.child_fd, 0)[1]
					except ChildProcessError:
						self.exit_code = 1

		return got_output

	def execute(self) -> bool:
		"""
		The main function behind ``SysCommandWorker()``.
		This is the function that executes the given command.
		It does so by forking into a child process using ``os.execve()``.
		After which it registers the file descriptor of the child process
		into a ``poll_object`` which can be used to determine if the process
		has any output to retrieve, which makes the whole operation non-blocking.
		"""
		import pty

		if (old_dir := os.getcwd()) != self.working_directory:
			os.chdir(str(self.working_directory))

		# Note: If for any reason, we get a Python exception between here
		#   and until os.close(), the traceback will get locked inside
		#   stdout of the child_fd object. `os.read(self.child_fd, 8192)` is the
		#   only way to get the traceback without loosing it.
		self.pid, self.child_fd = pty.fork()
		os.chdir(old_dir)

		if not self.pid:
			try:
				if storage['arguments'].debug:
					try:
						with open(f"{storage['LOG_PATH']}/cmd_history.txt", "a") as cmd_log:
							cmd_log.write(f"{' '.join(self.cmd)}\n")
					except PermissionError:
						pass

				os.execve(self.cmd[0], list(self.cmd), {**os.environ, **self.environment_vars}) # nosec
				if storage['arguments'].get('debug'):
					log(f"Executing: {self.cmd}", level=logging.DEBUG)

			except FileNotFoundError:
				log(f"{self.cmd[0]} does not exist.", level=logging.ERROR, fg="red")
				self.exit_code = 1
				return False

		self.started = time.time()
		self.poll_object.register(self.child_fd, EPOLLIN | EPOLLHUP)

		return True

	def decode(self, encoding :str = 'UTF-8') -> str:
		"""
		Returns a complete copy of the trace-log in a decoded fasion.
		Defaults to ``UTF-8``, should be adjusted if used on other locales.
		"""
		return str(self._trace_log.decode(encoding))


class SysCommand:
	def __init__(self,
		cmd :Union[str, List[str]],
		callbacks :Optional[Dict[str, Callable[[Any], Any]]] = None,
		start_callback :Optional[Callable[[Any], Any]] = None,
		peak_output :Optional[bool] = False,
		environment_vars :Optional[Dict[str, Any]] = None,
		working_directory :Optional[str] = './',
		remove_vt100_escape_codes_from_lines :bool = True):
		"""
		A more convenient wrapper around :ref:`SysCommandWorker` where care
		for the process lifecyles isn't as important.

		It's similar to ``subprocess.check_output()`` in that it will execute,
		and hand back the result of the process. But due to how the meta-functions
		are defined in this class, we can either iterate directly over it:
		``if b"some string" in SysCommand("ls -l")`` or we can check the exit code:
		``if SysCommand("ls -l").exit_code == 0`` and both will work fine.
		"""
	
		_callbacks = {}
		if callbacks:
			for hook, func in callbacks.items():
				_callbacks[hook] = func
		if start_callback:
			_callbacks['on_start'] = start_callback

		self.cmd = cmd
		self._callbacks = _callbacks
		self.peak_output = peak_output
		self.environment_vars = environment_vars
		self.working_directory = working_directory
		self.remove_vt100_escape_codes_from_lines = remove_vt100_escape_codes_from_lines

		self.session :Optional[SysCommandWorker] = None
		self.session = self.create_session()

	def __enter__(self) -> SysCommandWorker:
		"""
		Returns an instance of :ref:`SysCommandWorker` when used in
		context mode. This is to avoid the lack of certain features only
		:ref:`SysCommandWorker` has access to.
		"""
		return cast(SysCommandWorker, self.session)

	def __exit__(self, *args :str, **kwargs :Dict[str, Any]) -> None:
		"""
		This should not be used, but keeping it for possible future needs.
		"""
		if len(args) >= 2 and args[1]:
			log(args[1], level=logging.ERROR, fg='red')

	def __iter__(self, *args :List[Any], **kwargs :Dict[str, Any]) -> Iterator[bytes]:
		"""
		Iterates over any line in the trace log from the parent session.
		"""
		if self.session:
			for line in self.session:
				yield line

	def __getitem__(self, key :slice) -> Optional[bytes]:
		"""
		Returns a section of the trace-log, requires a slice to be given and not a string.
		"""
		if not self.session:
			raise KeyError(f"SysCommand() does not have an active session.")

		elif type(key) is slice:
			start = key.start if key.start else 0
			end = key.stop if key.stop else len(self.session._trace_log)

			return self.session._trace_log[start:end]
		else:
			raise ValueError("SysCommand() doesn't have key & value pairs, only slices, SysCommand('ls')[:10] as an example.")

	def __repr__(self, *args :List[Any], **kwargs :Dict[str, Any]) -> str:
		"""
		Returns a string representation of the parent sessions trace log.
		"""
		if self.session:
			return self.session._trace_log.decode('UTF-8')
		return ''

	def __json__(self) -> Dict[str, Union[str, bool, List[str], Dict[str, Any], Optional[bool], Optional[Dict[str, Any]]]]:
		"""
		Returns a JSON structure representing the parameters given
		upon startup of the process.
		"""
		return {
			'cmd': self.cmd,
			'callbacks': self._callbacks,
			'peak': self.peak_output,
			'environment_vars': self.environment_vars,
			'session': True if self.session else False
		}

	def create_session(self) -> SysCommandWorker:
		"""
		Initiates a :ref:`SysCommandWorker` session in this class ``.session``.
		It then proceeds to poll the process until it ends, after which it also
		clears any printed output if ``.peak_output=True``.
		"""
		if self.session:
			return self.session

		with SysCommandWorker(self.cmd, callbacks=self._callbacks, peak_output=self.peak_output, environment_vars=self.environment_vars, remove_vt100_escape_codes_from_lines=self.remove_vt100_escape_codes_from_lines) as session:
			if not self.session:
				self.session = session

			while self.session.ended is None:
				self.session.poll()

		if self.peak_output:
			sys.stdout.write('\n')
			sys.stdout.flush()

		return self.session

	def decode(self, fmt :str = 'UTF-8') -> str:
		"""
		Returns a *(by default)* ``UTF-8`` encoded string of the
		tracelog from the parent session.
		"""
		if self.session:
			return self.session._trace_log.decode(fmt)

		return ''

	@property
	def exit_code(self) -> Optional[int]:
		"""
		Returns the ``.exit_code`` of the parent session.
		"""
		if self.session:
			return self.session.exit_code
		else:
			return None

	@property
	def trace_log(self) -> Optional[bytes]:
		"""
		A wrapper for returning the ``._trace_log`` from the parent session
		without moving the trace-log pointer.
		"""
		if self.session:
			return self.session._trace_log
		return None