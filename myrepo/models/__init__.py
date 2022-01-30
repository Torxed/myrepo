from pydantic import BaseModel

class RepositoryStruct(BaseModel):
	core :bool = True
	extra :bool = True
	community :bool = True
	testing :bool = False