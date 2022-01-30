import pathlib
import shlex
import re
from argparse import ArgumentParser
from .environment.storage import storage
from .environment.paths import setup_destination
from .system.workers import SysCommand, SysCommandWorker
from .system.logger import log
from .models import RepositoryStruct
from .tooling.packages import sync_packages, update_repo_db

__author__ = 'Anton Hvornum'
__version__ = '0.0.1'
__description__ = "A tool to create your own Arch Linux repository"

# TODO: https://stackoverflow.com/questions/15889621/sphinx-how-to-exclude-imports-in-automodule

# Parse arguments early, so that following imports can
# gain access to the arguments without parsing on their own.
parser = ArgumentParser()

parser.add_argument("--path", default="/srv/repo", nargs="?", help="Where to setup the repository structure", type=pathlib.Path)
parser.add_argument("--core", default=True, action="store_false", help="Enables sync of the core repository")
parser.add_argument("--extra", default=True, action="store_false", help="Enables sync of the extra repository")
parser.add_argument("--community", default=True, action="store_false", help="Enables sync of the community repository")
parser.add_argument("--testing", default=False, action="store_false", help="Enables sync of the testing repository")
parser.add_argument("--multilib", default=False, action="store_false", help="Enables sync of the multilib repository")
parser.add_argument("--packages", default="base base-devel linux linux-firmware", nargs="?", help="Where to setup the repository structure", type=str)
parser.add_argument("--mirror-list", default="/etc/pacman.d/mirrorlist", nargs="?", help="Where to setup the repository structure", type=pathlib.Path)
parser.add_argument("--mirror-regions", default=None, nargs="?", help="Override /etc/pacman.d/mirrorlist and --mirror-list", type=str)
parser.add_argument("--architecture", default="x86_64", nargs="?", help="Override the default architecture of x86_64", type=str)
parser.add_argument("--debug", default=False, action="store_true", help="Enables extra verbosity to terminal output (DEBUG etc are always sent to journald)")
parser.add_argument("--skip-sig", default=False, action="store_false", help="Disables signature download and checks for new packages in repository")
parser.add_argument("--key", default=None, nargs="?", help="Defines which key to use as a signing key for the repository")

args, unknowns = parser.parse_known_args()

# sanitize
args.path = args.path.expanduser().absolute()
args.mirror_list = args.mirror_list.expanduser().absolute()
if (package_file := pathlib.Path(args.packages).expanduser().absolute()).exists():
	with package_file.open('r') as fh:
		args.packages = [x.strip() for x in fh.readlines()]
else:
	raise PackageError(f"Could not read package list {package_file}")
if args.mirror_regions:
	args.mirror_regions = shlex.split(args.mirror_regions)

# Store the arguments in a "global" storage variable
storage['arguments'] = args
storage['repositories'] = RepositoryStruct(core=args.core, extra=args.extra, community=args.community, testing=args.testing)
storage['mirrors'] = {'https://archlinux.org/packages/$repo/$arch/$package/download': None}

if args.mirror_list:
	mirror_list_on_file = {}
	with args.mirror_list.open('r') as fh:
		for line in fh:
			if len(line.strip()) == 0:
				continue
			elif line[0] == '#':
				continue

			if (definition := re.findall('Server.*?=', line, re.IGNORECASE)):
				url = line[line.find(definition[0]) + len(definition[0]):]
				mirror_list_on_file[url.strip()] = None

	if mirror_list_on_file:
		storage['mirrors'] = mirror_list_on_file
elif args.mirror_regions:
	raise NotImplemented(f"Cannot resolve mirror regions yet.")
else:
	# We cannot grab signatures from the default generic package url https://archlinux.org/packages/
	args.skip_sig = True