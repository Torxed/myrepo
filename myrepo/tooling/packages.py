import pathlib
import ssl
import urllib.request
import json
import logging
import glob
from ..system.logger import log
from ..system.workers import SysCommand
from ..models import PackageSearch, PackageSearchResult
from ..exceptions import PackageError
from ..environment.storage import storage

BASE_URL_PKG_SEARCH = 'https://archlinux.org/packages/search/json/?name={package}'
BASE_URL_PKG_CONTENT = 'https://archlinux.org/packages/search/json/?package={package}'
BASE_GROUP_URL = 'https://archlinux.org/groups/x86_64/{group}/'


def find_group(name :str) -> bool:
	# TODO UPSTREAM: Implement /json/ for the groups search
	ssl_context = ssl.create_default_context()
	ssl_context.check_hostname = False
	ssl_context.verify_mode = ssl.CERT_NONE
	try:
		response = urllib.request.urlopen(BASE_GROUP_URL.format(group=name), context=ssl_context)
	except urllib.error.HTTPError as err:
		if err.code == 404:
			return False
		else:
			raise err

	# Just to be sure some code didn't slip through the exception
	if response.code == 200:
		return True

	return False

def package_search(package :str) -> PackageSearch:
	"""
	Finds a specific package via the package database.
	It makes a simple web-request, which might be a bit slow.
	"""
	# TODO UPSTREAM: Implement bulk search, either support name=X&name=Y or split on space (%20 or ' ')
	ssl_context = ssl.create_default_context()
	ssl_context.check_hostname = False
	ssl_context.verify_mode = ssl.CERT_NONE
	response = urllib.request.urlopen(BASE_URL_PKG_SEARCH.format(package=package), context=ssl_context)
	data = response.read().decode('UTF-8')
	return PackageSearch(**json.loads(data))

class IsGroup(BaseException):
	pass

def find_package(package :str) -> PackageSearchResult:
	data = package_search(package)

	if not data.results:
		# Check if the package is actually a group
		if (is_group := find_group(package)):
			# TODO: Until upstream adds a JSON result for group searches
			# there is no way we're going to parse HTML reliably.
			raise IsGroup("Implement group search")

		raise PackageError(f"Could not locate {package} while looking for repository category")

	# If we didn't find the package in the search results,
	# odds are it's a group package
	for result in data.results:
		if result.pkgname == package:
			return result

	raise PackageError(f"Could not locate {package} in result while looking for repository category")

def download_package(package :str, url :str, destination :pathlib.Path, filename :str, include_signature=True) -> bool:
	if (url := urllib.parse.urlparse(url)).scheme and url.scheme in ('https', 'http'):
		with (destination/filename).open('wb') as output:
			output.write(urllib.request.urlopen(url.geturl()).read())

		if include_signature:
			with (destination/f"{filename}.sig").open('wb') as output:
				output.write(urllib.request.urlopen(f"{url.geturl()}.sig").read())

		return True

	raise PackageError(f"Unknown or unsupported URL scheme when downloading package: {[url.scheme]}")

def sync_packages(packages :str, path :pathlib.Path) -> None:
	# package_struct = {}

	repositories_to_update = []
	for package in packages:
		log(f"Synchronizing package: {package}", level=logging.INFO, fg="yellow")
		# package_struct[package] = {'category' : get_package_category(package)}
		try:
			package_info = find_package(package)
		except IsGroup:
			log(f"{package} is a group, not supported yet", level=logging.WARNING, fg="red")
			continue

		version = package_info.pkgver

		repo = package_info.repo
		database_path = path/repo/"os"/storage['arguments'].architecture
		log(f"Found package '{package}', version {version} in repo {repo}", level=logging.DEBUG)

		if not repo in repositories_to_update:
			repositories_to_update.append(repo)

		grabbed = False
		for mirror in storage['mirrors']:
			if not '$package' in mirror:
				mirror += '/$package'

			mirror_py_friendly = mirror.replace('$repo', repo)
			mirror_py_friendly = mirror_py_friendly.replace('$arch', storage['arguments'].architecture)
			mirror_py_friendly = mirror_py_friendly.replace('$package', package_info.filename)

			log(f"Attempting download from mirror {mirror}", level=logging.DEBUG)
			log(f"Mirror definition was converted to: {mirror_py_friendly}", level=logging.DEBUG)
			if download_package(package, mirror_py_friendly, database_path, package_info.filename, include_signature=storage['arguments'].skip_sig is False):
				grabbed = True
				break
		
		if not grabbed:
			raise PackageError(f"Implement pacman -Syw --cachedir --dbdir ...")

	for repo in repositories_to_update:		
		log(f"Updating repo {repo} with any new packages", level=logging.INFO)
		database_path = path/repo/"os"/storage['arguments'].architecture
		options = ['--new', '--remove', '--prevent-downgrade']

		for package_type in ['.pkg.tar.xz', '.pkg.tar.zst']:
			for package in glob.glob(f"{database_path}/*{package_type}"):
				if not (repo_add := SysCommand(f"repo-add {' '.join(options)} {database_path}/{repo}.db.tar.gz {package}")).exit_code in (0, 256):
					raise RepositoryError(f"Could not initiate repository {database_path}: [{repo_add.exit_code}] {repo_add}")