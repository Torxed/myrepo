import pathlib
import ssl
import urllib.request
import json
import logging
import glob
from typing import List
from ..system.logger import log
from ..system.workers import SysCommand
from ..models import PackageSearch, PackageSearchResult
from ..exceptions import PackageError, SysCallError
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

	if response.code != 200:
		raise PackageError(f"Could not locate package: [{response.code}] {response}")

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

def download_package(package :str, repo :str, url :str, destination :pathlib.Path, filename :str, include_signature=True) -> bool:

	if (url := urllib.parse.urlparse(url)).scheme and url.scheme in ('https', 'http'):
		destination.mkdir(parents=True, exist_ok=True)

		# If it's a repository we haven't configured yet:
		database_path = destination/f"{repo}.db.tar.gz"

		try:
			SysCommand(f"repo-add {database_path} __init__")
		except SysCallError as error:
			if error.exit_code not in (0, 256):
				raise RepositoryError(f"Could not initiate repository {database_path}: [{error.exit_code}] {error}")

		with (destination/filename).open('wb') as output:
			output.write(urllib.request.urlopen(url.geturl()).read())

		if include_signature:
			with (destination/f"{filename}.sig").open('wb') as output:
				output.write(urllib.request.urlopen(f"{url.geturl()}.sig").read())

		return True

	raise PackageError(f"Unknown or unsupported URL scheme when downloading package: {[url.scheme]}")

class VersionDef:
	major = None
	minor = None
	patch = None

	def __init__(self, version_string :str):
		self.version_raw = version_string
		if '.' in version_string:
			self.versions = version_string.split('.')
		else:
			self.versions = [version_string]

		if '-' in self.versions[-1]:
			version, patch_version = self.versions[-1].split('-', 1)
			self.verions = self.versions[:-1] + [version]
			self.patch = patch_version

		self.major = self.versions[0]
		if len(self.versions) >= 2:
			self.minor = self.versions[1]
		if len(self.versions) >= 3:
			self.patch = self.versions[2]

	def __eq__(self, other :'VersionDef') -> bool:
		if other.major == self.major and \
			other.minor == self.minor and \
			other.patch == self.patch:

			return True
		return False
		
	def __lt__(self, other :'VersionDef') -> bool:
		print(f"Comparing {self} against {other}")
		if self.major > other.major:
			return False
		elif self.minor and other.minor and self.minor > other.minor:
			return False
		elif self.patch and other.patch and self.patch > other.patch:
			return False

	def __str__(self) -> str:
		return self.version_raw

def sync_packages(packages :List[str], path :pathlib.Path, skip :List[str] = []) -> List[str]:
	# package_struct = {}

	repositories_to_update = []
	for package in packages:
		# Parsing of dependency version control
		target_version = None
		target_version_gt = False
		target_version_lt = False
		target_version_gt_or_eq = False
		target_version_lt_or_eq = False
		target_version_specific = False
		if '>=' in package:
			package, target_version = package.rsplit('>=', 1)
			target_version_gt_or_eq = VersionDef(target_version)
		elif '>' in package:
			package, target_version = package.rsplit('>', 1)
			target_version_gt = VersionDef(target_version)
		elif '<=' in package:
			package, target_version = package.rsplit('<=', 1)
			target_version_lt_or_eq = VersionDef(target_version)
		elif '<' in package:
			package, target_version = package.rsplit('<', 1)
			target_version_lt = VersionDef(target_version)
		elif '=' in package:
			package, target_version = package.rsplit('=', 1)

			if '-' in target_version:
				minimum, maximum = target_version.split('-', 1)
				target_version_gt_or_eq = VersionDef(minimum)
				target_version_lt_or_eq = VersionDef(maximum)
			else:
				target_version_specific = VersionDef(target_version)

		if package in skip:
			log(f"Package {package} already downloaded, skipping!", level=logging.DEBUG)
			continue

		else:
			log(f"Synchronizing package: {package}", level=logging.INFO, fg="yellow")
		
		try:
			package_info = find_package(package)
		except IsGroup:
			log(f"{package} is a group, not supported yet", level=logging.WARNING, fg="red")
			continue
		except PackageError:
			log(f"{package} could not be located in either of upstream package database or upstream group database, resorting to 'pkgfile'")
			found_fildep = False

			try:
				for line in SysCommand(f"pkgfile {package}"):
					target_repo, package_from_pkg = line.split(b'/')
					package_from_pkg = package_from_pkg.decode().strip()
					
					if getattr(storage['repositories'], target_repo.decode()) is False:
						continue

					repositories_to_update = list(set(repositories_to_update + sync_packages([package_from_pkg], path, skip)))
					
					skip.append(package_from_pkg)
					found_fildep = True
					package_info = find_package(package_from_pkg)
					
					break

				if found_fildep:
					continue

			except SysCallError:
				# Fallback, use `pacman -Ss` in an attempt to resolve the package
				for line in SysCommand(f"pacman --color never -Ss {package}"):
					package_from_pacman, version_def, *_ = line.split(b' ')
					target_repo, package_from_pacman = package_from_pacman.decode().split('/')

					if getattr(storage['repositories'], target_repo) is False:
						continue

					repositories_to_update = list(set(repositories_to_update + sync_packages([package_from_pacman], path, skip)))
					package_info = find_package(package_from_pacman)		

					found_fildep = True
					break

				if found_fildep:
					continue

				raise PackageError(f"Could not locate dependency {package} using pkgfile!")

		version = VersionDef(package_info.pkgver)
		if target_version:
			target_version = VersionDef(target_version)
			if target_version_gt and version < target_version:
				raise PackageError(f"Package {package} requires version newer than {target_version} but {version} was found")
			elif target_version_gt_or_eq and version < target_version and version != target_version:
				raise PackageError(f"Package {package} requires version newer or equal to {target_version} but {version} was found")
			elif target_version_lt and version > target_version:
				raise PackageError(f"Package {package} requires version older than {target_version} but {version} was found")
			elif target_version_lt_or_eq and version > target_version and version != target_version:
				raise PackageError(f"Package {package} requires version older or equal to {target_version} but {version} was found")
			elif target_version_specific and version != target_version_specific:
				raise PackageError(f"Package {package} requires version equal to {target_version} but {version} was found")

		repo = package_info.repo
		database_path = path/repo/"os"/storage['arguments'].architecture
		if (database_path/package_info.filename).exists:
			log(f"Package already in cache, skipping", level=logging.INFO)

		if getattr(storage['arguments'], repo) is False:
			raise PackageError(f"Repository --{repo} is not activated, package is blocked")

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
			if download_package(package, repo, mirror_py_friendly, database_path, package_info.filename, include_signature=storage['arguments'].skip_sig is False):
				grabbed = True
				break
		
		if not grabbed:
			raise PackageError(f"Implement pacman -Syw --cachedir --dbdir ...")

		skip.append(package)
		if package_info.depends:
			repositories_to_update = list(set(repositories_to_update + sync_packages(package_info.depends, path, skip)))

	return repositories_to_update

def update_repo_db(repo :str, path :pathlib.Path) -> bool:
	log(f"Updating repo {repo} with any new packages", level=logging.INFO)
	database_path = path/repo/"os"/storage['arguments'].architecture
	options = ['--new', '--remove', '--prevent-downgrade', '--sign']

	for package_type in ['.pkg.tar.xz', '.pkg.tar.zst']:
		for package in glob.glob(f"{database_path}/*{package_type}"):
			try:
				SysCommand(f"repo-add {' '.join(options)} {database_path}/{repo}.db.tar.gz {package}")
			except SysCallError as error:
				raise RepositoryError(f"Could not initiate repository {database_path}: [{error.exit_code}] {error}")

	return True