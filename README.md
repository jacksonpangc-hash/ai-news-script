# AI资讯口播 Skill

为面向中国大陆中小企业老板的 AI 应用博主，查近期新闻和真实使用案例，写成通俗、逻辑清楚、可直接念的中文口播。重点解释 **AI接手什么工作、产出怎样被业务使用、有什么有据价值**。

当前版本 **v1.6.0** · [下载完整 Skill](https://github.com/jacksonpangc-hash/ai-news-script/releases/tag/v1.6.0) · [使用说明](ai-news-script/USAGE.md) · [安装与云端更新](ai-news-script/INSTALL.md)

## 开始使用

1. 下载 `ai-news-script-v1.6.0.zip`，解压得到完整 `ai-news-script` 文件夹。
2. 将整个文件夹放到项目 `.agents/skills/`，确认入口是 `.agents/skills/ai-news-script/SKILL.md`。
3. 新开会话，确认实际加载 v1.6.0，然后直接说：

> 帮我查一下最近的AI新闻，做一篇抖音口播稿给我。

默认交一个标题、一篇连续中文口播、简短来源与检索截止时间。可以指定行业、地区、受众、时长，也可以只修改某一段。云端使用需上传本次完整ZIP；本地更新不会自动替换旧附件。

## 工作方式

- 从实际读过的近期事实中找AI分工，说明输入、处理、产物及业务用途；功能公告或示意输出不冒充实际使用。
- 默认大陆案例、滚动7天；必要时最多扩30天并披露。无足够证据时说明，不编造地区、工时、成本或成交效果。
- 区分任务产出、流程效率、业务信号和最终结果，不要求每稿都有ROI。
- 内置固定版本 [Sepia](https://github.com/Nanako0129/sepia)，先审中心、因果及信息增量，再作定向语言编辑；保留有用的问答和解释。
- 每轮最多8搜索、12网页读取、2轮改稿；支持不保存，运行记录只存授权工作区。

需要宿主已有的联网搜索和读页能力。辅助脚本仅需 Python 3.9+ 标准库，没有新模型、API账号或安装服务。不会生成视频、配音、自动发布或后台监控。

## 验证与边界

```sh
python -m unittest discover -s ai-news-script/tests -v
python -m unittest discover -s tests -p test_package.py -v
python tools/package_skill.py
```

程序测试验证记录、预算、存储和包边界，不证明新闻真实或文风必然合适。小样本文字审核不代表长期稳定出稿，也不保证播放量或爆款。默认定位可被用户明确要求覆盖。

发行包SHA256：`56c144a831d7edaae9555cba52f3e50d9856ca1a387aa297fe6ffe84e2eb322d`。完整包可从 Releases 下载，发行清单和校验文件存放在 [dist](dist/)。

## 许可与归属

本项目独立实现以 [MIT](LICENSE) 提供。内置 Sepia 0.12.4 固定 commit `fb06be76abeae7dd606960a32f2b10c1d1798e0d`，保留原文、版权和MIT许可；详见 [NOTICE](ai-news-script/NOTICE.md)。其他第三方仅作独立方法参考，不包含其未知许可原文。

公开仓库不包含真人范文、新闻全文、真实运行记录、用户历史、私人资料或开发对话。
