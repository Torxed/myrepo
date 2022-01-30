import pathlib
from .storage import storage
from ..system.workers import SysCommand
from ..exceptions import RepositoryError, SysCallError

def setup_destination(path :pathlib.Path) -> bool:
	for repo in storage['repositories']:
		database_path = path/repo[0]/"os"/storage['arguments'].architecture/f"{repo[0]}.db.tar.gz"
		# package_path = path/repo[0]/"os"/storage['arguments'].architecture/f"{{*.pkg.tar.xz,*.pkg.tar.zst}}"
		package_path = path/repo[0]/"os"/storage['arguments'].architecture/f"__init__"

		(path/repo[0]/"os"/storage['arguments'].architecture).mkdir(parents=True, exist_ok=True)

		try:
			SysCommand(f"repo-add {database_path} {package_path}")
		except SysCallError as error:
			if error.exit_code not in (0, 256):
				raise RepositoryError(f"Could not initiate repository {database_path}: [{error.exit_code}] {error}")