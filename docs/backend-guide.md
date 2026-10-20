# 小说助手 MVP：后端手写提示

更新时间：2026-10-20。

这是一份练习路线，不是完整实现。按顺序完成，每步跑通并验收后再继续；遇到问题，先根据提示定位，再看参考文档。后端代码由你手写。

## 1. 完成范围

本轮目标：前端提交小说设定、已有正文和续写要求，后端调用 OpenAI，返回可直接展示的续写文本；输入错误和模型服务异常都有明确的响应。

基本完成需要具备：

- `GET /health`：确认 HTTP 服务正在运行。
- `POST /generate`：校验输入、组织提示词、调用真实模型、返回续写结果。
- 环境变量配置、异步调用、客户端资源释放、超时和异常处理。
- 本地前端跨域访问、少量关键自动化测试、可复现的启动说明。

本轮是无状态的续写服务：每次请求携带本次需要的设定和正文；后端不自动记忆前一次生成。前端将需要保留的生成结果合并到正文，再发起下一次请求。

数据库、小说/章节 CRUD、登录、多 Agent、向量检索和 Docker 留到后续需求明确时再做。流式输出作为本文最后的可选进阶，不影响基本完成。

## 2. 当前起点与依赖

当前代码中已经有健康检查、请求模型、固定文本生成接口，以及绑定到接口的响应模型。`instruction` 的长度上限已经修正为 1000。还需要将响应字段 `result` 统一为 `text`，并补充全空白输入校验。

生产直接依赖保持简单：

| 包 | 用途 | 当前状态 |
| --- | --- | --- |
| `fastapi` | HTTP 路由、参数校验与接口文档 | 已声明 |
| `uvicorn` | 运行服务 | 已声明 |
| `pydantic` | 定义输入输出模型与校验规则 | 已声明 |
| `openai` | 官方 Python SDK | 到第 3 步时添加 |

配置用标准库 `os`，日志用 `logging`，测试断言与替身用 `unittest` / `unittest.mock`。暂不引入额外的配置框架或 LLM 封装框架。

## 3. 最终接口约定

### 健康检查

`GET /health` 成功返回 `200`：

```json
{"status": "ok"}
```

健康检查不调用模型，不验证账户余额，也不消耗模型额度。

### 续写

`POST /generate`，请求头使用 `Content-Type: application/json`：

```json
{
  "setting": "一座禁止做梦的城市",
  "content": "他第一次梦见了城墙外的海。",
  "instruction": "续写一段，保持悬疑感，只输出新增正文"
}
```

| 字段 | 类型 | 默认值 | 校验 |
| --- | --- | --- | --- |
| `setting` | `str` | `""` | 允许空，最长 10000 字符 |
| `content` | `str` | 无，必填 | 长度 1～20000，不能全为空白 |
| `instruction` | `str` | `"请继续写下去"` | 长度 1～1000，不能全为空白 |

为 `setting` 添加上限，是为了避免只有正文和要求受限，设定却能无限增大。以上数值是本项目的初始约定，不是 OpenAI API 的限制。

成功返回 `200`：

```json
{"text": "天亮后，他发现枕边多了一粒盐。"}
```

`text` 只包含新增正文。固定示例只用于第 1 步；接入模型后，实际输出不应写成响应模型的默认值。

输入校验失败沿用 FastAPI 默认的 `422` 与 `detail` 数组。模型服务异常使用本文第 6 步约定的 `detail` 字符串；前端区分这两种形状即可，不必现在重写全部错误格式。

## 第 1 步：收尾固定响应接口

**目标**：让请求模型、响应模型、实际 JSON 和 `/docs` 保持一致。

**要做的事**：

1. 将 `GenerateResponse.result` 改为 `text`，让该字段必填。
2. 在路由中显式构造响应模型，将固定续写文本传给 `text`。
3. 保留返回类型标注。已有的 `response_model` 也可以保留，两者指向相同类型即可。
4. 补齐接口约定中的长度和空白校验。

**提示**：

- `Field(default="")` 表示可以省略；没有默认值的字段才是必填。
- `min_length=1` 只检查长度，空格也是字符。
- 用 `@field_validator` 给 `content` 和 `instruction` 补充检查；默认的 `after` 模式可在内置字符串校验后执行。
- 判断 `not value.strip()` 时抛出 `ValueError`，通过后返回原始 `value`，保留正文缩进与换行。不要因此删掉已有长度限制。
- 这个校验器是类方法，注意 `@classmethod`、`cls` 参数以及最后的 `return`。

**验收**：

- 正常请求得到固定的 `{"text": "..."}`；`/docs` 中响应字段也是 `text`。
- 仅传 `content` 可以成功。
- 缺少正文、正文为空或全为空白、要求全为空白，都得到 `422`。
- 正文 20000 字符通过，20001 失败；要求 1000 通过，1001 失败；设定上限也分别检查边界。
- 正文中的有效缩进和换行不会被校验器修改。

参考：[Pydantic 字段校验器](https://pydantic.dev/docs/validation/latest/concepts/validators/#field-validators)、[FastAPI 响应模型](https://fastapi.tiangolo.com/tutorial/response-model/)。

## 第 2 步：准备配置与启动方式

**目标**：密钥和模型名称从环境读取，启动方式清楚，不添加配置依赖。

**要做的事**：

1. 规划 `OPENAI_API_KEY` 与 `OPENAI_MODEL` 两个必填环境变量。
2. 用 `os.getenv` 读取；检查缺失和纯空白，错误信息只写变量名。
3. 在仓库提供 `.env.example`，只放占位值；实际值由你填入本地 `.env`。
4. 在启动阶段校验配置，避免等到用户点击生成时才发现缺少密钥。第 4 步会将这部分接入 `lifespan`。

示例配置格式（不是可直接使用的凭据）：

```dotenv
OPENAI_API_KEY=replace_with_your_key
OPENAI_MODEL=replace_with_a_model_you_can_access
```

**提示**：

- 模型由你账户实际可用、支持 Responses API 的模型决定；不在代码里硬编码一个未经确认的名称。
- uv 可以加载 `.env`，无需额外安装 `python-dotenv`。
- 当前 `.gitignore` 已忽略 `.env`。示例文件只保留变量名和占位值。
- 不读取、不打印密钥来做调试；检查“是否存在”就足够了。

本地启动命令：

```powershell
uv run --env-file .env uvicorn main:app --reload
```

**验收**：缺少任意必填配置时，完成启动接入后会清楚报错；配置齐全时服务启动，日志不显示密钥。只校验字符串无法证明密钥和模型有访问权限，实际请求放在第 3 步确认。

参考：[uv run 环境文件选项](https://docs.astral.sh/uv/reference/cli/#uv-run)。

## 第 3 步：用小脚本复习 OpenAI SDK

**目标**：先独立理解一次模型调用，再接 HTTP 接口。

添加依赖：

```powershell
uv add openai
```

**要做的事**：写一个临时练习脚本，例如 `scripts/try_openai.py`，发起一次短文本生成，只打印生成正文。

**提示，按这个顺序查和写**：

1. 从 `openai` 导入 `AsyncOpenAI`。
2. 写一个 `async def main()`，用 `asyncio.run` 作为脚本入口。
3. 客户端从环境读取 `OPENAI_API_KEY`；模型名读取 `OPENAI_MODEL`。
4. 用异步上下文管理器管理客户端，练习进入和退出时的资源管理。
5. 用 `await client.responses.create(...)` 发起请求。
6. 第一遍只处理 `model`、`instructions`、`input`，读 `response.output_text`。
7. 加上明确的 `timeout` 和 `max_retries`。练习阶段可先设超时 60 秒、重试 0 次，便于观察错误；这是项目选择，不是 SDK 默认值。

不要将 Responses API 和 Chat Completions API 的参数及返回结构混用。这里练习的是 `responses.create` 与 `output_text`，不是 `choices[0].message.content`。

运行方式：

```powershell
uv run --env-file .env python scripts/try_openai.py
```

**验收**：在你明确准备调用后，脚本能完成一次真实生成，并在退出时关闭客户端。真实调用会使用 API 额度；后面的自动化测试用替身实现，不反复请求模型。

思考：`await` 等待的是什么？为什么在 FastAPI 的 `async def` 路由里直接调用同步网络客户端会占用事件循环线程？

参考：[OpenAI 官方 SDK 入口](https://developers.openai.com/api/docs/libraries)、[Responses Python 接口](https://developers.openai.com/api/reference/python/resources/responses/methods/create)。SDK 异步客户端、超时及重试参数的一个[官方示例](https://developers.openai.com/api/docs/guides/tools-computer-use)也可用于核对写法，只看客户端初始化部分，无需实现其中的工具功能。

## 第 4 步：把客户端接入应用生命周期

**目标**：应用运行期间复用客户端，结束时释放；续写期间健康检查仍可响应。

**要做的事**：

1. 使用 FastAPI 的 `lifespan`，启动时读取并校验配置、创建 `AsyncOpenAI`。
2. 通过 `app.state` 保存客户端和模型配置。
3. 退出生命周期时关闭客户端，使用异步上下文管理器或 `try/finally` 保证清理。
4. 将生成路由改为 `async def`，通过 FastAPI 的 `Request` 取得应用状态。

**提示**：

- `contextlib.asynccontextmanager` 来自标准库。
- `yield` 之前做启动准备，之后做退出清理。
- 请求体参数仍使用 `GenerateRequest`；HTTP 请求上下文使用另一个参数，例如 `http_request: Request`，避免混淆。
- 不在每次请求里新建一个长生命周期客户端，也不在请求间共享“当前小说正文”这种可变数据。
- 不在异步路由里调用 `asyncio.run`；它只用于独立脚本入口。

**验收**：启动和关闭流程正常；路由能取得客户端；一次生成等待模型时，另一个请求访问 `/health` 仍能返回。不把模型调用塞进健康检查。

参考：[FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/)。

## 第 5 步：实现真正的续写逻辑

**目标**：将用户输入变成清楚的写作请求，保持 HTTP 代码容易阅读。

**要做的事**：

1. 将生成逻辑抽成异步函数，例如 `generate_continuation(...) -> str`。
2. 路由负责接收已校验的参数、等待该函数、构造 `GenerateResponse(text=...)`。
3. 生成函数负责组织提示词、调用 SDK、检查响应、返回新增正文。

**提示**：

- 固定写作规则放在 `instructions`：延续人物和视角、尊重设定、只输出新增正文、不要重复已有正文或添加说明。
- 用户提供的设定、正文与要求放到 `input`，用清楚的段落标签区分；不要把小说中的对白拼进固定规则。
- `setting` 为空时仍可续写。提示词应能表达“未提供额外设定”。
- 正文字符数与模型 token 数不是一回事。长度校验不能保证所有模型都容纳得下输入。
- 可在服务端固定一个 `max_output_tokens` 上限控制输出规模；它不是中文字符数，部分模型的预算也包含推理 token。先核对所选模型，不给每种模型都套用一组额外参数。
- 读取 `response.status`，只在 `completed` 且 `output_text` 非空白时作为本版成功结果。
- `incomplete` 可能带有部分文本。本版先明确返回“生成未完成”，不要把部分文本当成完整成功；相关原因可从 `incomplete_details` 判断。
- 不要偷偷截断用户正文，也不要返回一个空字符串伪装成功。失败策略在第 6 步统一。

建议到这里再做小幅拆文件，而不是一开始建立多层目录：

```text
main.py              # app、lifespan、路由、HTTP 错误映射与 CORS
schemas.py           # 请求与响应模型
llm.py               # 提示词、SDK 调用、模型结果检查
config.py            # 环境配置读取和校验
tests/               # 第 8 步再添加
```

这些名字可以按实际调整；不必创建只有一行转发代码的类或模块。练习脚本中的调用最终应由 `llm.py` 的函数接替，避免长期维护两份业务逻辑。

**验收**：接口返回真实新增文本；改变续写要求能影响结果；设定为空可用；多次请求不串内容；未完成或空白输出不会被当成正常结果。

参考：[OpenAI 文本生成](https://developers.openai.com/api/docs/guides/text?lang=python)、[Responses 参数和状态](https://developers.openai.com/api/reference/python/resources/responses/methods/create)。

## 第 6 步：补齐失败路径

**目标**：前端能区别输入错误、上游故障和超时，不需要解析 Python 异常字符串。

下面是本项目的错误映射约定，可以用 `HTTPException` 实现：

| 情况 | 对外 HTTP 状态 | 给前端的说明 |
| --- | --- | --- |
| 输入不符合模型 | `422` | 沿用 FastAPI 校验详情 |
| SDK 请求超时 | `504` | 生成超时，请稍后重试 |
| 上游限流或暂时无额度 | `503` | 模型服务暂不可用，请稍后重试 |
| 网络连接失败、模型服务报错 | `502` | 模型服务请求失败 |
| 上游鉴权失败、模型不可用或参数被拒绝 | `502` | 模型服务配置或请求异常 |
| 生成未完成、无有效正文或模型拒绝生成 | `502` | 生成未完成或未获得可用正文 |
| 未预期的程序错误 | `500` | 服务内部错误 |

其中的 `502` 策略用于让初版保持简单；后续若需要区分拒绝、截断和部分结果，再扩充业务错误码或响应字段。

**提示**：

- 先认识 SDK 的 `APITimeoutError`、`RateLimitError`、`APIConnectionError`、`APIStatusError`。具体类放在宽泛的父类前捕获；超时异常也属于连接错误体系。
- 上游密钥是后端配置。上游返回 `401` 时，不要直接把它转成“当前前端用户未登录”。
- 对外返回稳定说明；服务端日志记录异常类型、上游状态、可用的请求 ID 和耗时。不要记录密钥、完整正文或完整上游错误体。
- 使用 `logging` 和 `time.perf_counter` 即可；一条请求结束日志加必要异常信息就够。
- SDK 重试和手写重试不要叠加。超时通常约束单次请求，增加重试会增加总等待时间；暂时保持第 3 步的重试 0 次。
- 捕获异常的范围尽量围绕生成调用；不要无条件捕获全部异常后返回 `200`。
- 先用测试替身模拟这些错误，不为验证每个异常反复发送真实请求。

**验收**：模拟超时得到 `504`，限流得到 `503`，上游故障和空结果得到 `502`；所有情况都不把敏感信息塞进响应，也不导致之后的健康检查失败。

参考：[OpenAI API 错误说明](https://developers.openai.com/api/docs/guides/error-codes)。异常类的具体继承关系可在安装后的 SDK 中查看。

## 第 7 步：准备本地前端联调

**目标**：TypeScript 前端能通过浏览器调用后端，跨域预检正常。

**要做的事**：

1. 使用 FastAPI 提供的 `CORSMiddleware`，不添加 CORS 包。
2. 允许本地前端实际使用的 origin；Vite 常见地址为 `http://localhost:5173`，以启动结果为准。
3. 如果同时使用 `127.0.0.1`，将对应 origin 单独加入。
4. 本版没有 Cookie 登录，保持 `allow_credentials=False`；允许实际需要的 `GET`、`POST` 方法及 `Content-Type` 请求头。

**提示**：

- 协议、主机名、端口共同决定 origin。`localhost` 与 `127.0.0.1` 不是同一个 origin。
- 浏览器跨域提交 JSON 可能先发 `OPTIONS`，由中间件处理，不需要另写预检路由。
- CORS 是浏览器访问规则，不是身份验证。
- `/docs` 能调用成功不能证明跨域配置正确，需要实际浏览器请求或显式的预检测试。
- 前端请求体只发送接口字段，不携带 OpenAI 密钥。

**验收**：允许来源的浏览器请求能读取结果；预检响应包含匹配的允许来源；未允许来源不会获得允许访问的 CORS 响应头。若前端尚未建立，先验预检，把真实浏览器验证留待联调时补上。

参考：[FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/)。

## 第 8 步：关键测试与交付说明

**目标**：无需真实 API 调用就能检查主要行为，换一台有 uv 的电脑也能按说明启动。

可继续使用标准库 `unittest`，通过 FastAPI 的 `TestClient` 测接口。`TestClient` 需要 `httpx`，到此时再作为开发依赖添加：

```powershell
uv add --dev httpx
uv run python -m unittest discover -s tests -v
```

**测试提示**：

- 用 `unittest.mock.AsyncMock` 替代异步生成函数或 SDK 调用。要替换代码实际查找该符号的位置，留意直接导入和模块导入的区别。
- HTTP 层用替身检查输入、成功响应和错误映射；另外少量测试覆盖生成函数对状态、空结果的判断，避免只模拟掉生成逻辑却完全没检查它。
- 用 `with TestClient(app) as client:` 触发生命周期；测试中设置虚拟环境变量，客户端不能发出真实网络请求。若启动逻辑后续增加网络行为，也要一起替换。
- 准备合成的短正文，不把私人稿件写进测试。
- 检查行为，不断言某次真实模型恰好生成哪句小说。

建议覆盖的关键情况：

| 场景 | 验收结果 |
| --- | --- |
| 健康检查 | `200`，不调用生成函数 |
| 合法请求与省略可选字段 | 返回 `text`，默认值传递正确 |
| 缺失、空、全空白及越界输入 | `422`，不调用模型 |
| 有效正文包含缩进和换行 | 传入生成函数的正文未被改写 |
| 成功模型响应 | 提取正文并符合响应模型 |
| 超时、限流、上游错误 | 分别映射约定的状态 |
| `incomplete`、空白输出、拒绝输出 | 不当作成功 |
| CORS 预检 | 允许来源通过，不允许来源无授权头 |

**整理 README**：

1. 项目用途和当前功能范围。
2. Python 版本、`uv sync`、环境变量和启动命令。
3. `/health`、`/generate` 的请求及响应示例。
4. 错误状态说明、测试命令。
5. 明确本版不保存稿件；每次请求自行携带上下文。

保留 `uv.lock` 以复现依赖；不将 `.venv` 和真实 `.env` 纳入版本管理。

参考：[FastAPI 测试](https://fastapi.tiangolo.com/tutorial/testing/)、[uv 项目管理](https://docs.astral.sh/uv/guides/projects/)。

## 基本完成清单

- [ ] 输入输出字段与本文接口约定一致。
- [ ] 边界长度、空白校验和默认值正确。
- [ ] 配置缺失能在启动时定位，密钥仅在服务端使用。
- [ ] 真实模型续写成功，生成过程中健康检查仍能响应。
- [ ] 客户端在生命周期内复用，退出时关闭。
- [ ] 超时、上游故障、未完成和空输出都有明确失败响应。
- [ ] 本地跨域预检通过，接口已具备前端联调条件。
- [ ] 关键测试通过，测试不依赖真实 API 额度。
- [ ] README 足以让人从安装依赖走到第一次请求。

到这里，后端基本功能完成。前端尚未开始时，真实浏览器联调单独记录为待验收；它不要求提前搭建完整前端。

## 可选进阶：流式续写

基本功能完成后再做。保留现有 `/generate`，另外提供 `POST /generate/stream`，避免同时改变普通接口行为。

**提示**：

- SDK 请求启用 `stream=True`，异步遍历事件，处理 `response.output_text.delta`，并识别完成、未完成及错误事件。
- HTTP 层使用流式响应，将文本增量编码成统一事件，例如 `delta`、`done`、`error`。可用标准库 `json` 生成 SSE 的 `data:` 内容，事件以空行分隔；正文中的换行要正确编码。
- 前端使用 `fetch` 发 POST 并读取响应流。原生 `EventSource` 主要面向 GET，不适合直接承接这里的 JSON POST 请求体。
- 响应开始前的错误可以返回 HTTP 错误；开始推送后无法再修改 HTTP 状态，需要流内错误事件，且失败后不能再发送成功完成事件。
- 客户端断开时停止读取并关闭上游流，考虑取消传播；不要假设每个网络分块恰好是一个完整事件。
- 验收正常增量、中文与换行、上游中途错误、客户端取消，以及资源是否关闭。

参考：[OpenAI 流式响应](https://developers.openai.com/api/docs/guides/streaming-responses)。
