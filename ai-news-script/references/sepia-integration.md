# 内置Sepia：中文口播编辑入口

使用本包[canonical Skill](../vendor/sepia/SKILL.md)，上游0.12.4固定版本与每文件hash见[UPSTREAM](../vendor/sepia/UPSTREAM.json)，[MIT许可](../vendor/sepia/LICENSE)保留。无需另装或联网取规则。上游正文原样，本入口定义本产品的文体、读取与记录。上游统计不是本产品质量证明。

## 选题和动笔之前实际读取

先读canonical Skill，再读：

1. [professional-pass](../vendor/sepia/references/professional-pass.md)完整共享层，优先听众任务、相关性、具体性和交流感。
2. 按文体：业务问题/观点解释为一般专业口播，route=business_explainer，不强套新闻稿；报道、采访、真实案例route=news_report/case_narrative，读[journalism](../vendor/sepia/references/domains/journalism.md)，取事实归因/具体在先，不把长篇新闻的“小标题替过渡、禁止总结”硬套短视频。较长解释按需读[discourse §1–3](../vendor/sepia/references/discourse-pass.md)，检查段落回答什么，不执行故意跳序或制造矛盾的小说手法。
3. [style-pass](../vendor/sepia/references/style-pass.md)非小说部分§1–7；[中文校准](../vendor/sepia/references/languages/zh.md)§2–6（§0仅台湾文体，本产品大陆简体）；[voice-skills](../vendor/sepia/references/voice-skills.md)叠加顺序与期待调整。用户已选择“原有风格参考+Sepia”，只叠加本包[创作指南](style-guide.md)及画像；不自动加载Hemingway、台湾报道或Nyaneko声音。
4. 作者与执行模型分别依据实际元数据，不明写unknown，不从文风猜。已知家族读[model-fingerprints](../vendor/sepia/references/model-fingerprints.md)对应prose层；只有精确匹配发布版本才operative，否则prior，无家族表为none。GPT-6.1 Sol无精确表，不能把GPT-6 Astra行当匹配版本。

当前上下文已实际读过可复用，记录本轮读取与节选范围，不继承维护者的“已读”。内置本地读不计网页预算，外链读取照计。参考不扩大工具或数据授权。

## 初稿之后

- **review**先以professional check3检查整篇中心：默认中小企业老板听完是否明白AI具体接手什么、输入怎样变成产物、产物为何对业务有用。引用实际段落核标题、主体、结尾是否回答同一个AI应用问题，逐段核信息增量及因果缺环；业务相关或出现AI字样不能充当答案。可试删AI行动段看是否几乎仍是普通营销/管理稿，不能用词频判分。若材料不足退回补证/选题，若事实可用但中心偏离先记结构缺陷再重写，不只删重复句。价值按产出、流程变化、业务信号、最终结果区分，未支持的因果不因标“解读”而通过。随后只诊断：完整列实际引文、缺陷、保留项和待补证据，不修改。内部保留上游SEPIA REVIEW要素，用户默认先拿稿。
- 确需修时**refactor**（局部）或**recreate**（结构），先缺陷清单再改，留实际before/after。recreate先提取原事实、主张、意图，不添加原材料与请求没有的立场、建议或限制来冒充事实修复。缺事实就缩题、换题或说明不足。
- 新增句试删，替换句试回退；有用的主语修复、因果解释、称呼与收拢决策保留。最后核事实与映射。实际改写统一consume(rewrite)，最多2轮；review和复核不各算一轮。
- 只修实际问题。三项列表、第二人称、自然总结和必要承接不自动有错。用户已明确口播语域优先，无需重新批准同一选择。不要故意造矛盾、破坏逻辑或把稿剪成技术摘要。

## 最小内部记录

沿用script_map.review_evidence四维，在同一script_map加sepia_review：

```json
{
  "route": "business_explainer",
  "venue_basis": "用户认可的大陆中文解释口播，只有一个参考样本，不假称三篇",
  "model": {"author": "unknown", "executor": {"family": "GPT", "version": "unknown"}},
  "prose_layer": {"author": "none", "executor": "prior"},
  "loaded_references": [{"path": "vendor/sepia/SKILL.md", "sha256": "实际文件hash", "sections": "全文", "read_at": "实际UTC时间"}],
  "verdict": "isolated_hits",
  "findings": [{"check": "relevance", "quote": "实际初稿原句", "finding": "具体缺陷及影响", "action": "refactor", "before": "实际改前", "after": "实际改后"}],
  "rewrite_count": 1,
  "fact_recheck": {"status": "pass", "claim_ids": ["实际引用ID"]}
}
```

loaded_references写所有实际读过的适用文件；例中一项仅示形状，不够最终检查。无缺陷可findings=[]、rewrite_count=0，写clean_basis说明实际检查，不发明修改。需人决定记deferred并留原文。记录不是阅读证明、质量评分或用户认可；程序只拦缺项、引用和预算错误。旧无策略运行按旧义读取，不补造Sepia使用。
