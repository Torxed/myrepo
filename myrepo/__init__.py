import pathlib
from argparse import ArgumentParser
from .environment.storage import storage
from .system.workers import SysCommand, SysCommandWorker
from .system.logger import log
from .models import RepositoryStruct

__author__ = 'Anton Hvornum'
__version__ = '0.0.1'
__description__ = "A tool to create your own Arch Linux repository"

# TODO: https://stackoverflow.com/questions/15889621/sphinx-how-to-exclude-imports-in-automodule

# Parse arguments early, so that following imports can
# gain access to the arguments without parsing on their own.
parser = ArgumentParser()

parser.add_argument("--path", default="/srv/repo", nargs="?", help="Where to setup the repository structure", type=pathlib.Path)
parser.add_argument("--core", default=True, action="store_true", help="Enables sync of the core repository")
parser.add_argument("--extra", default=True, action="store_true", help="Enables sync of the extra repository")
parser.add_argument("--community", default=True, action="store_true", help="Enables sync of the community repository")
parser.add_argument("--testing", default=False, action="store_true", help="Enables sync of the testing repository")

# Store the arguments in a "global" storage variable
args, unknowns = parser.parse_known_args()
storage['arguments'] = args
storage['repositories'] = RepositoryStruct(core=args.core, extra=args.extra, community=args.community, testing=args.testing)