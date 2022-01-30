import json
from typing import Any

class JsonEncoder:
	@staticmethod
	def _encode(obj :Any) -> Any:
		"""
		This JSON encoder function will try it's best to convert
		any archinstall data structures, instances or variables into
		something that's understandable by the json.parse()/json.loads() lib.
		_encode() will skip any dictionary key starting with an exclamation mark (!)
		"""
		if isinstance(obj, dict) and not hasattr(obj, 'json'):
			# We'll need to iterate not just the value that default() usually gets passed
			# But also iterate manually over each key: value pair in order to trap the keys.

			copy = {}
			for key, val in list(obj.items()):
				if isinstance(val, dict):
					# This, is a EXTREMELY ugly hack.. but it's the only quick way I can think of to trigger a encoding of sub-dictionaries.
					val = json.loads(json.dumps(val, cls=JSON))
				else:
					val = JsonEncoder._encode(val)

				if type(key) == str and key[0] == '!':
					pass
				else:
					copy[JsonEncoder._encode(key)] = val
			return copy
		elif type(obj) == bytes:
			return obj.decode()
		elif hasattr(obj, 'json'):
			try:
				return json.loads(obj.json())
			except TypeError:
				raise TypeError(f"Could not convert JSON data returned by {obj} back into a Python JSON serializable structure.")
		elif isinstance(obj, (list, set, tuple)):
			return [json.loads(json.dumps(item, cls=JSON)) for item in obj]
		else:
			return obj

class JSON(json.JSONEncoder, json.JSONDecoder):
	"""
	A safe JSON encoder that will omit private information in dicts (starting with !)
	"""
	def _encode(self, obj :Any) -> Any:
		"""
		A wrapper for JsonEncoder._encode
		"""
		return JsonEncoder._encode(obj)

	def encode(self, obj :Any) -> Any:
		"""
		A wrapper for json.JSONEncoder.encode() using the _encode() funciton above.
		"""
		return super(JSON, self).encode(self._encode(obj))