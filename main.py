from fastapi import FastAPI
from pydantic import BaseModel,Field,field_validator
# create a fastapi instance named app
app = FastAPI()

DEFAULTS = {
    "setting": "",
    "content": "",
    "instruction": "请继续写下去"
}

class GenerateRequest(BaseModel):
    setting: str = Field(default="")
    content: str = Field(..., min_length=1,max_length=20000)
    instruction: str = Field(default="请继续写下去",min_length=1,max_length=1000)
    @field_validator("setting","content","instruction")
    @classmethod
    def check_not_empty(cls, v):
        if not v:
            raise ValueError("字段不能为空")
        return v

class GenerateResponse(BaseModel):
    text: str = Field(..., min_length=1,max_length=20000)

@app.get("/health")
def healthcheck():
    """Health check endpoint."""
    return {"status": "ok"}

@app.post("/generate",response_model=GenerateResponse)
def generate_text(text: GenerateRequest)-> GenerateResponse:
    
    return GenerateResponse(text=text.content)

#思考：min_length=1拦不住空格输入，如果不导入新的方法，那么要回填之后再做校验，类定义处只约束上界