import pathlib
from .storage import storage
from ..system.workers import SysCommand
from ..exceptions import RepositoryError

def setup_destination(path :pathlib.Path) -> bool:
	for repo in storage['repositories']:
		database_path = path/repo[0]/"os"/storage['arguments'].architecture/f"{repo[0]}.db.tar.gz"
		# package_path = path/repo[0]/"os"/storage['arguments'].architecture/f"{{*.pkg.tar.xz,*.pkg.tar.zst}}"
		package_path = path/repo[0]/"os"/storage['arguments'].architecture/f"__init__"

		(path/repo[0]/"os"/storage['arguments'].architecture).mkdir(parents=True, exist_ok=True)


		if not (repo_add := SysCommand(f"repo-add {database_path} {package_path}")).exit_code in (0, 256):
			raise RepositoryError(f"Could not initiate repository {database_path}: [{repo_add.exit_code}] {repo_add}")