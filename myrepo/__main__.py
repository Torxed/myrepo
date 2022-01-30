import importlib
import sys
import pathlib

if pathlib.Path('./myrepo/__init__.py').absolute().exists():
	spec = importlib.util.spec_from_file_location("myrepo", "./myrepo/__init__.py")
	myrepo = importlib.util.module_from_spec(spec)
	sys.modules["myrepo"] = myrepo
	spec.loader.exec_module(sys.modules["myrepo"])
else:
	import myrepo

if myrepo.storage['arguments'].path:
	print(myrepo.storage['arguments'].path)