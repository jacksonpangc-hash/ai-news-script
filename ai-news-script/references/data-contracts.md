# 数据契约 1.1（兼容读取1.0）

## 存放与版本

新运行五份UTF-8 JSON统一首层`schema_version: "1.1"`，未知null，ID与外键明确。旧`1.0`可读取和渲染，仍按旧规则检查，不自动补实用门槛或feed覆盖，不能称为通过1.1。五份混版或未知版本拒绝；history/preferences未变，继续1.0。真实记录在授权工作区`runtime/ai-news-script/<workspace-path-sha256-prefix>/<profile_id>/runs/<run_id>/`；控制检查点另放同profile的`pending/<run_id>.json`。时间戳UTC用Z，只有日期保留date精度，不补时分秒。

workspace_id由当前授权根的真实路径散列生成；不同根即使profile同名也隔离。profile_id只接受非个人信息的字母数字/横线/下划线。此是本地目录隔离，不是多租户认证；不扫描别的profile。拒绝路径穿越与runtime子路径符号链接，原子替换文件、短锁合并历史/偏好。残留锁需检查中断写者，不能盲删他人的锁。

run_id为UTC+随机后缀。已保存运行不覆盖，修订生成新run_id及parent_run_id。save_history=false不创建任何文件或目录，也不写偏好。用户明确单独要求导出才写指定结果，不能顺便打开全部持久化。

## 五个运行JSON

每份首层都有schema_version、run_id。下列字段由Agent填写，不要求用户输入。

| 文件 | 内容 |
|---|---|
| run.json | request、time_context、config、capabilities、budget、status、outcome、coverage、errors、output；可加tool_log |
| sources.json | sources数组 |
| stories.json | stories数组、selected_story_ids |
| fact_cards.json | claims、metrics、enterprise_cases数组 |
| script_map.json | revision、title、sentences、checks，可加title_claim_ids |

`run.request`：text、language、audience、topic_scope、strict_window、duration_seconds、style_profile_id、parent_run_id；1.1新增research_mode=full/fixed_source_regression/local_revision，默认full，只有固定材料/局部续改可用后两者。topic_scope默认practical_cases，兼容both/frontier_only/enterprise_only。`time_context`：now_utc、effective_timezone、timezone_origin、window_start_utc、window_end_utc、window_type、lookback_days_used、expanded、content_mode。content_mode=recent_news/expanded_window/evergreen，阻塞可null。自然日请求要由Agent设置相应边界与window_type。

status按顺序 initialized→capability_checked→scanning→deduplicated→screened→selected→deep_read→fact_checked→drafted→reviewed→saved→delivered；可在中途转blocked/failed/canceled。outcome独立为null/delivered/delivered_with_limits/blocked/failed/canceled。saved只是保存阶段，不证明用户收到；无保存模式也可在会话走过saved阶段。

capabilities含search_web、open_source、local_storage的available/unavailable/not_checked及host_name、adapter_verified。budget含search_calls_used、open_calls_used、rewrite_passes_used、retries_by_source、exhausted。调用前扣；失败/重试/批量子项照算。coverage有frontier、enterprise（not_requested/not_searched/searched_with_qualified_result/searched_no_qualified_result/partially_blocked/blocked）、blocked_source_ids、limitations。errors每项stage/code/source_id/retryable/attempt/message（脱敏）。output含selected_story_ids、script_path、sources_path、history_saved、duration_estimate_seconds、duration_method。

## 来源和事件

source必填：source_id、url、canonical_url、title、publisher、source_kind、published_at、updated_at、retrieved_at、access、independence_group、evidence_notes。

source_kind=official_release/official_documentation/official_case/research_paper/independent_reporting/community_post/aggregator/other。
日期对象为`{value, precision: date|timestamp, timezone}`；未知null。
access包含status（ok/partial/blocked/not_found/transient_error/not_read）、read_level（full_text/visible_excerpt/search_snippet/metadata_only/none）、visible_sections、audio_seen、visual_seen、transcript_seen、block_reason。evidence_notes每项locator及observed_summary，只保必要摘记，不存整文。

story必填：story_id、canonical_event_key、event_identity（entity/action/object/version/event_date，日期含source_ids）、channel（1.0仅frontier/enterprise，1.1也允许personal/business）、source_ids、date_status(supported/ambiguous/future_unverified/conflicting/outside_window)、history_match、material_update、evidence_gate、editorial_score、angle、selected。evidence_gate含passed、checks、rejection_reasons。门槛checks为readable_core_evidence/entity_and_event_clear/date_conflict_resolved/maturity_not_overstated/no_invented_testing_or_results，全部为true才入选。未过门槛editorial_score必须null；评分结构见editorial-rubric。应用主分类由value_brief.domain表达，不把发现路线当分类。

canonical_event_key按可审计身份形成，语义相同由Agent合并，日期纠正记录历史aliases。material_update至少description/new_claim_ids/source_ids；历史落盘时增加run_id。只有实质新事实或用户repeat_requested才重讲。

## 1.1实用价值与发现路线

每个候选需`practical_value_gate: {decision: pass|reject|needs_evidence, reason, claim_ids}`；非pass不评分，入选必须pass。入选story新增短`value_brief`：

- domain兼容原personal_efficiency/enterprise_efficiency/business_operations/business_model，新增daily_life/learning/light_work/personal_creation；application_context=actual_use/pilot/demonstration；outcome_evidence_type=quantified/qualitative。纯功能演示/拟议不合格，demonstration仅指公开已完成具体任务。
- beneficiary_task、before、after、changed_mechanism、result_evidence分别为`{text, claim_ids}`。各1–2句，复用已有事实与解释依赖，不另建事实库。不得为填before编造旧耗时。
- cost_boundary为`{value, unknown_reason, text, claim_ids}`。未知成本value=null、原因not_disclosed等，说明范围；已知值须引用。
- editorial_bridge为`{text, claim_ids}`，一小段内部散文连接具体听众、主问题、最强证据及带走的有限判断，不要求机械三句。程序检查引用和非空，叙事关系由Agent复核。

新披露历史案例另记news_basis=recent_disclosure、disclosed_at日期及source_ids、case_occurred_at日期及source_ids或null；event_identity.action=disclose_case、event_date对应披露，不把执行改到近期。仅网站刷新无新增披露不合格。

run新增`discovery_routes.builder_feed: {feeds:[...]}`及`official_case_search: {status, attempt_ids}`。旧版无supplementary_v1的完整研究须实际尝试三个精确配置URL；1.4新运行可按策略不启用，见下文；固定回归/局部续改明确research_mode，不重跑发现。每feed包含url、status（ok/ok_empty/failed/stale/not_attempted）、generated_at、observed_at、items_count、window_items_count、qualified_items_count、qualification_note、attempt_ids、error，另可有author_count、unknown_date_count、leads及omitted_window_items。条目日期决定是否在窗内，生成时间只判断流是否陈旧；未筛完/未知合格数为null并说明。空流不能写成失败；失败不能写成0个合格结果。

run.tool_log每次为`{call_id, kind, discovery_channel, query或url, outcome, timestamp, source_id或lead_id, fallback_of}`，fallback_of无替代时null。调用前扣预算并记reserved，实际调用后补真实outcome；reserved不算完成覆盖。feed attempt_ids关联真实open的精确URL，官方搜索关联真实query；fallback须指原调用。新适配器返回最小条目线索（lead_id/url/title/summary/published_at/date_status/specific_document），并不证明案例实际改善；频道链接不可伪称读过节目。旧coverage.frontier/enterprise仍是主题覆盖，不能等价替换为发现路由。结构检查无法证明真实调用发生，必须保留可核查工具证据与Agent审查。

## 事实、案例、指标

claim必填claim_id/story_id/claim_type/statement/support_status/evidence/qualifiers/depends_on_claim_ids/allowed_in_script。
claim_type=fact/source_opinion/assistant_interpretation；support_status=supported/attributed_only/disputed/insufficient。核心未核实默认不入稿。evidence每项source_id/locator/relationship/observed_summary；关系如direct/supporting/contradicting。解释句可无直接证据，但须有明确非循环依赖，不可在“解释”中新增数字、已发生结果或保证。

case必填case_id/story_id/organization/business_process/problem/input/ai_action/human_role/output/integration/deployment_status/evidence_basis/independently_supported_claim_ids/deployment_scope/cost/cost_unknown_reason/metric_ids/limitations/claim_ids。缺字段的业务内容用null，不编流程。成熟度与证据性质分别取研究规则中的枚举。

metric必填metric_id/story_id/name/unit/baseline/outcome/sample_size/denominator/timeframe/method/cost/cost_unknown_reason/limitations/derived。baseline/outcome为null或`{value,scope,source_ids}`；timeframe含start/end。derived为`{eligible,value,formula,unit,ineligible_reasons}`。口径不明或不一、基线0时eligible=false,value=null。derive_metric仅给可比数据的相对变化和适用时百分点，不替代人工口径确认。cost未知null，unknown_reason=not_disclosed/not_checked/inaccessible/not_applicable。

## 映射与质检

sentence必填sentence_id/paragraph_index/text/sentence_kind/claim_ids/required_qualifiers_present。sentence_kind=factual/attributed/interpretive/rhetorical/mixed；除纯修辞外须映射完整主张。段索引非负递增，同段可多句。标题的主张同样核对，可用title_claim_ids映射。

checks必填schema/references_exist/factual_sentence_coverage/semantic_fact_review/dates_and_numbers/attribution_and_maturity/no_fabricated_first_person_experience/text_listenability/hook_promise_fulfilled，值pass/fail/not_run/not_applicable；最终稿各项实际完成才pass。actual_audio_listened布尔，默认false，issues数组。脚本不能判定一句话是否隐藏事实、归因是否真实存在或映射语义是否蕴含；这三者必须人工/Agent逐句复核。

正文唯一来源为映射，render_output自动列实际用到的来源并派生前置时间披露。时长用编辑参考速度，宽区间取整，不冒称计时。

1.1的script_map再加`review_evidence`数组，每项`{check, sentence_ids, basis_claim_ids, finding, change}`。至少覆盖actual_value/explanation_chain/natural_expression/fact_fidelity；finding引用实际句子，解释为何改善或有限制；change为具体改动或null。只写pass/通过不合格。字段与引用存在不等于语义、连贯或好听；这是Agent编辑证据，不是用户认可。user_style_confirmation另在开发交付记录中保持pending，只有用户认可才改。

## Python接口

在宿主Python会话把本Skill的scripts目录放入sys.path，再导入模块；不向磁盘暂存no-save运行。

- discovery：parse_feed解析真实feed形状与条目日期；discover(run, reader, before_call)逐源预算预扣/真实读取/记录，reader可注入离线fixture；生产默认HTTPS标准库读取。practical_contract.validate_practical只检查1.1结构与引用，不是语义质量评分器。
- normalize_records：normalize_url(url)、date_status(date_record,start,end)、derive_metric(metric)、editorial_total(score)、rank_stories(stories)、independent_groups(sources)。最后一项只按已标家族计数，不自动判断独立性。
- manage_state：new_run(request,now=None,timezone=None,preferences=None,overrides=None,parent_run_id=None)；生产不传固定now，测试才固定。resolve_config(preferences,overrides)；consume(run,kind,count=1,source_id=None,retry=False,block_reason=None)；transition(run,status,reason=None)；expand_window(run,evergreen=False)。
- 持久化：save_checkpoint(workspace,profile,run)、save_bundle(workspace,profile,bundle)、record_delivery(workspace,profile,run_id)；load_history、repeat_allowed、load_preferences、save_preference(key/value/explicit/authorization_summary/save_history)。持久化键只允许表达偏好，不能改安全配置。检查点有递增checkpoint_revision；旧版本冲突必须先重读，不允许减少已用预算或重试次数。每次实际调用前consume并在可保存模式下写检查点。
- revise_paragraph(bundle,index,replacements)返回新版本并标复核not_run，不改输入；事实纠错先回源再调用。
- validate_records：validate_bundle(bundle,final=False)返回错误数组；load_bundle(directory)。bundle键是run/sources/stories/fact_cards/script_map，各值对应整个JSON文件。
- render_output：render(bundle)返回script/sources/conversation及duration信息。no-save时直接会话输出，不调用落盘。

## 历史与偏好

event_history.json顶层schema_version/revision/events；每事件canonical_event_key/event_identity/last_delivered_at/delivered_run_ids/angles_used/material_updates，可加aliases。只交付成功后更新；历史与运行收据是两次原子写，交付记账幂等，可在中断后重放同一run_id。

preferences.json顶层schema_version/profile_id/preferences，可加revision；每项key/value/scope:durable/authorized_at/authorization_summary。只明确长期要求才写。save_history=false优先，本次明确“记住”也不写，告知未持久记住。当前一次改稿不改变默认。

## v1.2编辑记录（schema仍为1.1）

不新增必填字段或版本。editorial_bridge.text说明观看理由→主问题→最强已核细节→收尾判断，claim_ids引用现有主张。editorial_score.rationale区分案例合格、材料篇幅与角度成立，不用总分替代判断。review_evidence.finding先指出具体弱点与未兑现承诺，change写实际改动或未改理由，复核事实/解释/自然表达/实用价值。未知表现不补零，自评不冒充用户确认。

画像中的原创虚构示例只作表达索引，不能导入fact_cards作为真实案例；外部样本的权利、完整性和表现记录在项目维护目录，不进入普通运行历史。保留旧契约读取、唯一映射渲染与定点修改接口。

## v1.3最小兼容扩展（文件schema仍为1.1）

只放宽有依据的任务分类，不回填旧记录。旧1.0/1.1文件按原意义读取；旧版本校验器不认识新增枚举，需升级本Skill，不能声称新记录能被旧程序全部接受。原actual_use/pilot无需演示字段，不自动加演示标签。

新domain为daily_life（日常）、learning（学习）、light_work（轻办公）、personal_creation（个人创作），保留四个旧值。默认配置default_case_focus指导选材，不覆盖明确行业请求；audience=everyday_ai_curious，原profile_id保留稳定标识，画像revision随包版本更新。

application_context=demonstration须value_brief.demonstration_evidence：input_claim_ids、output_claim_ids均非空且引用可用于稿件、有实际可读来源的claims；scope_limit为非空范围说明。只有搜索摘要、未知引用或不可用主张不能充输入/结果证据。正文仍须由Agent判断任务确已完成、产物是不是实际观察；结构字段不证明内容真实。来源渲染自动标demonstration及scope_limit，不能把演示改标actual_use避校验。

before可说明原始输入/愿望/原状态，不强填旧工时；after与result_evidence落到实际成品/候选。editorial_bridge连接观看理由、输入→产物、最亮差异和收尾；review_evidence允许真实换中心/换角度/换题，不只记删术语。现有五JSON、唯一正文、隔离、预算、no-save和定点修改接口保留。

## v1.3.1实际执行依据（schema仍为1.1）

新建运行固定`config.task_execution_policy="required_v1"`，配置不可设off或null。所有入选actual_use/pilot/demonstration均须在value_brief新增：

```json
{"execution_evidence":{"kind":"author_execution_report","claim_ids":["execution_claim"],"summary":"来源明确记载实际提交输入并取得结果的动作"}}
```

kind另允许recorded_execution、local_reproduction。claim_ids非空，引用allowed_in_script=true的fact；support_status为supported或attributed_only；来源status为ok/partial，read_level为full_text/visible_excerpt，evidence.relationship为direct/supporting。解释、示意清单、未读或冲突依据不能通过，错误码task_execution_unconfirmed。作者自述可作为执行依据，但必须保留自述归因，不等于独立复现。字段存在只证明结构，Agent还需核语义是否真是执行记录。

demonstration仍另有输入、输出和scope_limit。历史无策略标记的记录继续可读，渲染明确提示历史兼容、未按当前执行证据审核；不自动升级旧记录或重写历史。普通调用采用新策略。duration_policy=material_first_not_a_quota，duration_seconds/target_characters是软参考；不以字数区间机械拒绝有据短稿。

### v1.3.1编辑复核记录的语义

沿用四维review_evidence和change可为null，不增加评分/必填字段。explanation_chain需指明句子新增的解释关系，不能只列讲述顺序。natural_expression需记录实际删段/删句对照：删除后观众损失的事实、解释、承接或体验；无实质损失就删/合并，有用则保留，不强制造改动。无亲测、无六段、用户pending等属于事实/范围，不替代听感检查。结构验证仍不能证明这些判断真实完成，完整正文和实际修改对照必须由Agent审阅。

## 1.4地区与补充发现（schema仍为1.1）

新运行config含region_policy=mainland_first_v1、region_scope=mainland_preferred、builder_feed_policy=supplementary_v1。new_run默认复制region_scope到request；用户明确覆盖用overrides={"region_scope":"..."}，再在request.region_scope_reason具体记其要求。可选mainland_only/overseas_only/global/user_specified。旧记录无标记继续原语义，不伪造新地区验证通过。

每个候选新增case_region：
```json
{"case_region":{"value":"china_mainland","basis_type":"location_of_use","text":"可读来源明确的实际使用场景所在地","claim_ids":["location_fact"]}}
```
value另有hong_kong/macau/taiwan/overseas/unknown；basis_type为location_of_use/location_of_user/explicit_case_location，已知地区须引用可读fact，不能用语言/域名/模型国籍/姓名当依据。未知为value=unknown、basis_type=unknown、text写缺口、claim_ids可空。字段结构不证明语义正确，Agent需核对来源实际说的地方。

默认/仅大陆的完整研究，在任何海外/全球搜索之前，需已有两个不同大陆角度的真实成功搜索覆盖。tool_log每项仍走official_case_search，新增region_focus=china_mainland与search_angle，原query不同；失败和原查询重试保留，按预算计，成功覆盖不足不能伪报完成。明确用户覆盖不要求先大陆。rank_stories(stories,minimum=60,region_scope=run["request"]["region_scope"])只在原合格池先按地区选择，再按原编辑分，不设地域评分。

run.region_review含mainland_result=not_attempted/qualified/insufficient、fallback_reason、expansion_decision及expansion_reason。默认选非大陆时须insufficient与具体补查缺口；expansion_decision可为expanded_to_30_days（time_context确实已扩窗）、strict_window（用户确实限制日期）、not_useful（具体说明延长日期为何补不了当前证据缺口）。mainland_only不能回退；overseas_only须确有海外依据。地区未知也不能冒充大陆。固定材料/局部改稿不重跑检索。

补充feed仍保留三个精确URL记录，但无固定预留读取：discovery.discover(run,urls=[某配置URL],...)可只读选定项；默认大陆策略调用它前须完成两个大陆检索角度。discovery.skip_feeds(run,reason)将未启用项记not_enabled，reason为mainland_evidence_sufficient/user_scope/supplementary_not_needed；保留attempt_ids=[]、生成时间/计数/合格数=null、error=null，不产生假调用，不耗预算。mainland_evidence_sufficient仅适用于已选大陆且region_review记qualified。not_attempted+budget_exhausted仅用于真正尝试预扣预算失败，不是按策略不启用的代称。旧记录无新flag仍检查旧三feed要求。

sources/claims/script_map等唯一正文与原子存储结构不变；natural_expression现同时记录具体句子的文本口播检查，不把人物、条件、关键机制删没来换短句。

## v1.5最小编辑与加载扩展（文件schema仍为1.1）

新运行config增加sepia_policy=embedded_review_v1、editorial_policy=audience_problem_v15、default_non_mainland_fallback=false。new_run按实际当前入口读取loaded_identity：name/version/entry_path/entry_sha256/package_id/expected_version/verification，verification=actual_entry_bytes。启动时指定版本应先用loaded_identity.read_identity(root,expected_version)检查；版本不符明示，不继续旧包。包标识与ZIP hash不同。

script_map增加sepia_review，完整字段、读取与修改语义以[Sepia集成入口](sepia-integration.md)为真源；只新增结构及引用检查，不改正文唯一映射。实际改稿仍共用budget.rewrite_passes_used最多2次，review本身不改稿。记录读过的适用文件、具体缺陷/保留/前后对照、模型与事实复核，不把字段存在当阅读或编辑质量证明。

rank_stories新增allow_non_mainland参数，旧调用默认True保持历史接口；新调用传config.default_non_mainland_fallback。v1.5默认国内不足不自动海外/未知凑稿；明确用户全球/国外范围照请求。地区可由境内业务或用户/任务场景证明，不要求私人地址。旧无新标记记录照旧验证，不补造新能力或改历史。

## v1.6定位与AI价值（schema仍为1.1）

默认audience=mainland_sme_owners，default_case_focus=enterprise_efficiency/business_operations，topic_scope=practical_cases；editorial_policy=ai_business_value_v16。用户明确覆盖仍优先，旧audience_problem_v15和历史记录按原义读取。无新增必填JSON字段：在原value_brief/editorial_bridge解释企业任务、输入→AI动作→产物→业务使用及有据价值；不能只有泛业务关联。原四维review_evidence与sepia_review用实际正文核中心、因果、增量、口语和同题收尾，不靠程序语义打分。

预扣便捷接口：tool_calls.prepare_call(run,call,workspace=None,profile='default')返回已预扣并持久化的新run；只传一个字典。complete_call(run,call_id,outcome,workspace=None,profile='default')记录真实完成结果，失败也不退预算。no-save仅返回内存数据。任何异常先停止外部调用；宿主工具权仍独立，接口不承诺跨宿主强制阻止。
