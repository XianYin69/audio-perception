# 不复述api_key

## 规则

1. 网关密钥只从 `<SMS_HOME>/config/config.json` 的 `llm_gateway.api_key` 直读，
   仅用于构造 `Authorization` 请求头。
2. 禁止出现在：stdout/stderr、任何产物文件、异常文本、日志、编码 JSON、
   判读 JSON、提示词、文档示例、提交信息。
3. 需要展示配置时只打印非敏感字段（base_url/model/max_tokens/temperature/top_p/timeout），
   密钥以 `sk-xx...` 掩码形式呈现。
4. 网关报错只回显状态码与响应体前 300 字符；若怀疑含密钥须截断后再打印。
5. 判读结果的 `usage` 只回填 model/prompt_tokens/completion_tokens。
6. 用户粘贴含密钥的文本时不复述、不写入产物，提示其轮换。

## 违规后果

- 密钥入对话历史与缓存 → 泄露不可撤回；
- 入产物文件 → 随技能打包分发，扩散到他人环境。

## 相关

- [resistance](../resistance.md)
- [网关文本调用](../../knowledge/网关文本调用.md)
- [scripts/_cli.py](../../scripts/_cli.py)
