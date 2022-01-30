from typing import Optional

class RequirementError(BaseException):
	pass

class SysCallError(BaseException):
	def __init__(self, message :str, exit_code :Optional[int] = None):
		super(SysCallError, self).__init__(message)
		self.message = message
		self.exit_code = exit_code