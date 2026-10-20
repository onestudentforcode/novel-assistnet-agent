from fastapi import FastAPI
from pydantic import BaseModel,Field
# create a fastapi instance named app
app = FastAPI()

class GenerateRequest(BaseModel):
    setting: str = Field(default="")
    content: str = Field(..., min_length=1,max_length=20000)
    instruction: str = Field(default="请继续写下去",min_length=1,max_length=1000)
class GenerateResponse(BaseModel):
    result: str = Field(default="天亮后，他发现枕边多了一粒盐。")
@app.get("/health")
def healthcheck():
    """Health check endpoint."""
    return {"status": "ok"}

@app.post("/generate",response_model=GenerateResponse)
def generate_text(request: GenerateRequest)-> GenerateResponse:
    return GenerateResponse()

#思考：min_length=1拦不住空格输入，如果不导入新的方法，那么要回填之后再做校验，类定义处只约束上界