import hashlib
import os
import subprocess
import re
from typing import Union
from ..exceptions import RequirementError

def locate_binary(name :str) -> str:
	for PATH in os.environ['PATH'].split(':'):
		for root, folders, files in os.walk(PATH):
			for file in files:
				if file == name:
					return os.path.join(root, file)
			break # Don't recurse

	raise RequirementError(f"Binary {name} does not exist.")

def gen_uid(entropy_length :int = 256) -> str:
	return hashlib.sha512(os.urandom(entropy_length)).hexdigest()

def pid_exists(pid: int) -> bool:
	try:
		return any(subprocess.check_output(['/usr/bin/ps', '--no-headers', '-o', 'pid', '-p', str(pid)]).strip())
	except subprocess.CalledProcessError:
		return False

def clear_vt100_escape_codes(data :Union[bytes, str]):
	# https://stackoverflow.com/a/43627833/929999
	if type(data) == bytes:
		vt100_escape_regex = bytes(r'\x1B\[[?0-9;]*[a-zA-Z]', 'UTF-8')
	else:
		vt100_escape_regex = r'\x1B\[[?0-9;]*[a-zA-Z]'

	for match in re.findall(vt100_escape_regex, data, re.IGNORECASE):
		data = data.replace(match, '' if type(data) == str else b'')

	return data