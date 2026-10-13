# 研究任务身份隔离与部署验收

更新：2026-10-13。范围仅为 `/api/async/**` 的任务提交与查询；不是任务持久化、取消或全站鉴权改造。

## 已实现的信任链

1. 浏览器仍向 Java 提交原有请求，并携带正常登录凭证。
2. `ResearchJobController` 只从认证拦截器写入的 `request.userId` 属性取得所有者，不信任浏览器的 owner 请求头、查询参数或 JSON 字段。
3. Java 序列化一次请求体，用**实际发送的 UTF-8 字节**生成签名。Python 验签后才接受该所有者并读取/创建任务。
4. 任务注册表强制保存 `owner_id`；查询必须匹配。其他用户、任务不存在、已过期、历史无 owner 记录均返回相同的 404，不返回结果或真实所有者。
5. ID 使用完整 UUID；随机 ID 只是降低碰撞风险，不能代替所有者校验。

Python 端没有“本地请求免签”“缺 owner 使用共享账号”兼容分支。即使浏览器能访问本机 5001 端口、或全局 CORS 允许跨域，也不能仅靠伪造 owner 头读取任务。

## 签名协议 v1

两端复用配置中的 `JWT_SECRET`，不传输密钥。Python 用 `SecretStr` 保存配置，不在响应中返回密钥。

```text
derived_key = HMAC-SHA256(UTF8(JWT_SECRET), UTF8("research-jobs-v1"))
body_hash   = lowercase_hex(SHA256(raw_body))
canonical   = owner + "\n" + timestamp + "\n" + METHOD + "\n" + path + "\n" + body_hash
signature   = lowercase_hex(HMAC-SHA256(derived_key, UTF8(canonical)))
```

- 请求头：`X-Research-Owner`、`X-Research-Timestamp`、`X-Research-Signature`。
- owner 为正的有符号 64 位整数；timestamp 为 Unix 秒，允许时钟偏差不超过 60 秒。
- METHOD 大写，path 为 `/api/async/...` 路径，不使用客户端提供的 owner 查询参数。
- GET 签空请求体；POST 签最终序列化字节。请求体上限 256 KiB。
- Python 使用 constant-time `compare_digest`；篡改身份、时间、方法、路径或请求体均不能沿用原签名。
- 签名不等于幂等：窗口内同一有效提交重放仍可能创建多个任务。请求幂等键与持久化另行实现。

## 发布前置条件

`backend` 与 `data-service` 必须使用**同一份、非公共默认值、至少 32 UTF-8 字节的高熵 `JWT_SECRET`**。不要把实际值提交到仓库或粘贴到测试报告。

`docker-compose.yml` 已为 Python 服务增加该环境变量传递，不再提供不安全默认密钥。本轮未读取或修改实际 `.env` 密钥，未部署容器。

| 情况 | 结果 |
|---|---|
| 密钥未配置、过短、公共默认值或其两侧空白变体 | 503，明确配置错误 |
| 两端密钥不一致、签名缺失/篡改/过期 | 401 |
| 身份有效，但任务不属于该用户/不存在/无 owner | 404，同一响应 |
| 已签名但请求体过大 | 413，不入队 |
| 已签名但 JSON 非对象/损坏/过深嵌套 | 400，不入队 |
| 队列满 | 429，不创建幽灵任务 |

不要用公开默认密钥让新入口“暂时跑起来”。若已有安全密钥，只需保证两端传入一致；若更换现有 JWT 密钥，既有登录令牌也会失效，需要重新登录。

## 验证与部署顺序

1. 先运行离线测试：Python `tests/test_research_auth.py` / `tests/test_research_jobs.py`；Java `ResearchJobAuthTest` / `ResearchJobOwnershipTest` / `ResearchJobDataServiceTest`。
2. 中英文 JSON、空 GET 的固定向量在两种语言中一致；Java MockRestServiceServer 还检查了实际发送字节和签名一致。
3. 维护窗口确认没有需要保留的运行中研究任务，再一同发布 Java 与 Python。只更新一端会导致新旧协议不匹配，应预期请求失败，而不是关闭验签。
4. 在验收环境用两个独立登录用户验证：A 可查询自己的任务，B 查询 A 的 ID 与随机不存在 ID 均为 404；浏览器提交的 owner 字段不能改变归属。
5. 生产验收只查询已有任务或在明确的数据/算力预算内运行，不把单元测试接到生产数据服务。

当前任务仍在单进程内存中，重启会丢失；结果保留 1 小时/最多 40 份。前端超时不等于后台取消。上述限制继续记录在 `TASKS.md` 的 R3，不因本次权限修复而关闭。
