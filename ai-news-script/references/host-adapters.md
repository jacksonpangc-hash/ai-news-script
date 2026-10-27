# 宿主能力与适配

本Skill提供研究和写作流程，不提供独立模型、搜索服务或API。每次运行发现实际search/open/time/file工具，再绑定能力；不要照抄某宿主的工具名称。优先使用宿主已有搜索和公开读页；无工具则明确阻碍，不编最近新闻，不自动安装服务或登录。

## Python与公开feed

辅助程序需要Python 3.9+，仅标准库，无pip依赖。discovery.py仅能读取配置内三份精确HTTPS URL（1.4按需启用，可只读一份或不读），有超时和体积上限，不下载运行仓库。每页/每次失败均先扣读取预算；合法替代调用另计并标fallback_of。证书验证失败不关闭TLS验证。

`--run -`接受stdin、返回stdout；no-save时只在会话/内存中组织JSON，不能先写临时文件。普通保存使用manage_state中的工作区/profile隔离与原子写入。存储API见[数据契约](data-contracts.md)。

## 能力降级

- 无Python：Agent手工履行同样证据、预算、日期契约；机械检查标NOT_RUN，不自动安装。
- 无写权限：会话交稿，说明未保存。
- 无联网搜索/读页：不能提供已核实近期资讯，说明缺口。
- 页面受限：不绕过登录、付费墙、验证码；在预算内找公开原始替代，不拿搜索摘要充完整读取。
- 图片无法实际显示：不描述未见画面；若文字已足够，可缩小到文字能证实的任务。

## 安装与验证边界

[Agent Skills规范](https://agentskills.io/specification)和[OpenAI技能说明](https://learn.chatgpt.com/docs/build-skills)支持文件结构与发现位置。将整个ai-news-script放入目标项目.agents/skills/，在新会话确认发现；也可按路径明确调用。

辅助脚本能运行、模型按路径读取、宿主自动发现、独立上下文行为和平台传播效果是不同证据。CLI或显式读包通过，不自动证明所有桌面选择器或其他Agent兼容。详见[安装](../INSTALL.md)。

## 1.6可靠预扣样例

普通宿主调用优先用scripts/tool_calls.py把预扣和检查点作为一个操作。每个search/open子项分别prepare_call；只传一个call字典，避免显式关键字与**item冲突。保存成功才返回新快照；异常时禁止继续调用外部工具，先解决错误或结束，不能在finally里联网。宿主仍掌握工具执行，接口不能强制所有宿主遵守。

```python
from tool_calls import prepare_call, complete_call
# call包含call_id、kind、discovery_channel、query或url、source_id或lead_id；
# 大陆检索另有region_focus/search_angle，fallback_of无替代为None。
run = prepare_call(run, call, workspace=workspace, profile=profile)
# 只有上一行成功返回后，宿主才调用实际search/open。
# 实际失败也要complete，预算不退；此处不把假工具函数当真实调用。
run = complete_call(run, call['call_id'], actual_outcome,
                    workspace=workspace, profile=profile)
```

跨工具调度时同样先检查预扣工具返回exit_code。no-save使用相同API仅更新内存，不先写临时文件。complete失败后先重读最新检查点再修复记录，不能重放已调用的工具来伪造完成。旧consume/save_checkpoint接口保留供历史与discovery兼容。
