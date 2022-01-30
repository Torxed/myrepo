import hashlib
import os
import subprocess
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