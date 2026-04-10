import { expect, test } from "@playwright/test";

function svgDataUri(label, hue = 36) {
  const markup = `
    <svg xmlns="http://www.w3.org/2000/svg" width="800" height="480" viewBox="0 0 800 480">
      <defs>
        <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stop-color="hsl(${hue} 62% 92%)" />
          <stop offset="100%" stop-color="hsl(${hue + 24} 54% 84%)" />
        </linearGradient>
      </defs>
      <rect width="100%" height="100%" fill="url(#g)" rx="28" />
      <text x="50%" y="50%" font-size="34" text-anchor="middle" fill="rgba(58,44,26,.72)" font-family="Noto Serif SC, serif">${label}</text>
    </svg>
  `;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup)}`;
}

function createIllustration(sceneId, candidateIndex, label, isCanonical = false) {
  return {
    id: Number(`${sceneId}${candidateIndex}`),
    scene_id: sceneId,
    url: svgDataUri(label, 30 + candidateIndex * 8),
    thumbnail_url: svgDataUri(`${label} 缩略`, 34 + candidateIndex * 8),
    candidate_index: candidateIndex,
    is_canonical: isCanonical,
    prompt_text: `镜头延续主角神情与服装识别度，候选 ${candidateIndex} 强调更稳的浅色电影感。`,
  };
}

function createDialogue(sceneId, orderIndex, speaker, content, locked = false) {
  return {
    id: Number(`${sceneId}${orderIndex}`),
    order_index: orderIndex,
    speaker,
    parenthetical: "",
    content,
    is_locked: locked,
    is_user_edited: locked,
    last_editor_type: locked ? "user" : "agent",
  };
}

function createScene(chapterOrder, sceneOrder) {
  const sceneId = chapterOrder * 100 + sceneOrder;
  const illustrations = [
    createIllustration(sceneId, 1, `第${chapterOrder}章 场${sceneOrder}`),
    createIllustration(sceneId, 2, `第${chapterOrder}章 场${sceneOrder} 主图`, true),
    createIllustration(sceneId, 3, `第${chapterOrder}章 场${sceneOrder} 夜景`),
  ];
  return {
    id: sceneId,
    order_index: sceneOrder,
    title: sceneOrder === 1 ? "雨棚下的试探" : "走廊尽头的回声",
    scene_type: sceneOrder === 1 ? "INT." : "EXT.",
    location: sceneOrder === 1 ? "旧广播楼大厅" : "电台后巷",
    time_of_day: sceneOrder === 1 ? "NIGHT" : "DAWN",
    cast_names: ["林见川", "沈昭", "迟野"],
    objective: "让人物在同一目标上产生错位，逼出情绪与信息落差。",
    emotional_tone: sceneOrder === 1 ? "克制、迟疑、带一点危险感" : "冷静外壳被轻微撕开",
    visual_prompt:
      "浅色电影感、纸张质地、人物五官稳定、服装层次明确、灯光偏米白和冷灰，保留短剧式情绪钩子。",
    is_locked: sceneOrder === 2,
    is_user_edited: sceneOrder === 2,
    last_editor_type: sceneOrder === 2 ? "user" : "agent",
    dialogue_blocks: [
      createDialogue(sceneId, 1, "林见川", "你不是来听节目的人，你是来确认我还敢不敢继续往下说。"),
      createDialogue(sceneId, 2, "沈昭", "我只是想知道，你到底是在救人，还是在把所有人一起拖进来。", true),
      createDialogue(sceneId, 3, "迟野", "你们再慢一分钟，楼下那辆车就会把答案带走。"),
    ],
    illustrations,
  };
}

function createNarrativeBlock(chapterOrder, orderIndex, locked = false) {
  const id = chapterOrder * 10 + orderIndex;
  const content =
    orderIndex === 1
      ? "夜色像一层没有彻底干透的灰墨，贴在广播楼的玻璃上。林见川站在录音台前，指节轻轻敲着桌沿，像在给自己计时，也像在给楼里每一扇没关严的门计时。"
      : orderIndex === 2
        ? "她知道这一章必须慢一点，把人先留在气氛里，再把危险递过去。于是每一句话都被压得很轻，轻到听众会怀疑这是不是一场失误，只有真正熟悉她的人才听得出，那是她准备翻盘前才会有的平静。"
        : "走廊尽头亮着一盏偏白的壁灯，光线不像照明，更像一条给人后退用的边界。沈昭停在那条边界之外，没再往前半步，却把林见川所有想回避的事都一件件提了出来。";
  return {
    id,
    order_index: orderIndex,
    content,
    is_locked: locked,
    is_user_edited: locked,
    last_editor_type: locked ? "user" : "agent",
  };
}

function createChapter(orderIndex, status) {
  const scenes = orderIndex <= 4 ? [createScene(orderIndex, 1), createScene(orderIndex, 2)] : [];
  const narrativeBlocks =
    orderIndex <= 4
      ? [
          createNarrativeBlock(orderIndex, 1),
          createNarrativeBlock(orderIndex, 2, orderIndex === 3),
          createNarrativeBlock(orderIndex, 3),
        ]
      : [];
  const pendingInterventions =
    orderIndex === 5
      ? [
          {
            id: 8805,
            chapter_id: 1000 + orderIndex,
            intervention_type: "rewrite_writer",
            reviewer_notes: "这一章的人物动机偏弱，Reviewer 建议重写高潮段的情绪推进。",
            suggested_guidance: "保留广播事故线，但把沈昭的决定改成更主动。",
            user_guidance: "",
            status: "pending",
          },
        ]
      : [];

  return {
    id: 1000 + orderIndex,
    order_index: orderIndex,
    title: orderIndex === 3 ? "第二次试音" : `第 ${orderIndex} 章的钩子标题`,
    summary: "章节围绕直播事故、人物错位与关系试探推进，尾声要留下下一章的动作钩子。",
    chapter_goal: "让主角在公开表达和真实动机之间产生可见裂缝。",
    hook: "节目还没结束，真正要来的人已经到了楼下。",
    status,
    is_locked: orderIndex === 2,
    continuity_notes:
      orderIndex <= 4
        ? [
            "Reviewer：林见川在本章里保持压低情绪的表达节奏，没有突然转成外放口吻。",
            "Reviewer：沈昭与迟野的立场拉扯清晰，但下一章要继续收束时间线，避免跳时感。",
          ]
        : [],
    narrative_blocks: narrativeBlocks,
    scenes,
    pending_interventions: pendingInterventions,
    latest_revision: narrativeBlocks.length
      ? {
          id: 7000 + orderIndex,
          summary: "Writer 初稿经 Reviewer 修订后回填。",
          created_by: "agent",
          revision_kind: "reviewer_apply",
          narrative_block_count: narrativeBlocks.length,
          scene_count: scenes.length,
        }
      : null,
    source_story_bible_revision_id: 3202,
  };
}

function buildProjectFixture() {
  const chapters = [
    createChapter(1, "scenes_ready"),
    createChapter(2, "drafted"),
    createChapter(3, "scenes_ready"),
    createChapter(4, "drafted"),
    createChapter(5, "needs_regeneration"),
    createChapter(6, "planned"),
    createChapter(7, "planned"),
    createChapter(8, "planned"),
    createChapter(9, "planned"),
    createChapter(10, "planned"),
  ];

  const libraryCharacters = [
    {
      id: 201,
      name: "林见川",
      role: "深夜电台主播",
      personality: "冷静、自持、在临界点才显露攻击性",
      goal: "查出事故真相并守住节目话语权",
      speech_style: "句子短，留白多，不轻易给出结论",
      appearance: "短发，浅灰外套，眼神有疲惫感",
      relationships: "与沈昭互相试探，与迟野处于危险合作",
      signature_line: "我不是要把真相说完，我只是要让沉默先露出破绽。",
      linked_project_ids: [101],
      reference_images: [{ id: 1, url: svgDataUri("林见川参考", 24) }],
      visual_profile: {
        visual_anchor: "浅灰外套、低饱和短发、细窄轮廓、克制眼神",
        signature_palette: "纸白、烟灰、旧金",
        silhouette_notes: "瘦削笔直，肩线锋利",
        wardrobe_notes: "长风衣与轻薄针织内搭",
        atmosphere_notes: "像一张被灯光压过的胶片",
      },
    },
    {
      id: 202,
      name: "沈昭",
      role: "调查记者",
      personality: "敏锐、稳准、情绪不轻易外露",
      goal: "在报道与私人情感之间保持平衡",
      speech_style: "逻辑强，提问带刀锋",
      appearance: "深色西装，利落长发，五官清晰",
      relationships: "与林见川存在旧事，与迟野互相防备",
      signature_line: "我不是来拆台的，我只是来确认你还撑不撑得住。",
      linked_project_ids: [101],
      reference_images: [{ id: 2, url: svgDataUri("沈昭参考", 52) }],
      visual_profile: {
        visual_anchor: "深色西装、明确眉眼、利落长发",
        signature_palette: "象牙白、深棕、夜蓝",
        silhouette_notes: "线条利落，步态稳定",
        wardrobe_notes: "修身西装与极简衬衫",
        atmosphere_notes: "像冷静的刀背反光",
      },
    },
    {
      id: 203,
      name: "迟野",
      role: "地下消息贩子",
      personality: "松弛、危险、擅长把筹码说成玩笑",
      goal: "在局势失控前拿到最值钱的信息",
      speech_style: "半真半假，常用反问",
      appearance: "米色夹克，浅色衬衫，带一点不修边幅",
      relationships: "与林见川合作不稳，与沈昭互不信任",
      signature_line: "你们都想赢，但今天先活着离开再谈赢。",
      linked_project_ids: [101],
      reference_images: [],
      visual_profile: {
        visual_anchor: "浅色夹克、松散姿态、带笑的危险感",
        signature_palette: "米白、黄铜、旧木色",
        silhouette_notes: "重心松散但行动迅速",
        wardrobe_notes: "轻夹克与略皱衬衫",
        atmosphere_notes: "像被雨水打湿过的火星",
      },
    },
    {
      id: 204,
      name: "叶槐",
      role: "制片人",
      personality: "克制、现实、擅长做最冷的判断",
      goal: "保证节目活下来",
      speech_style: "不说废话",
      appearance: "白衬衫，深色长裙",
      relationships: "与主角组形成外部压力",
      signature_line: "你们可以追真相，但别让节目先死。",
      linked_project_ids: [],
      reference_images: [],
      visual_profile: null,
    },
  ];

  const jobs = [
    {
      id: 9001,
      project_id: 101,
      chapter_id: 1003,
      scene_id: null,
      job_type: "chapter_draft",
      status: "processing",
      progress: 64,
      status_message: "Writer 已完成初稿，Reviewer 正在压口吻与时间线。",
      error_message: "",
      created_at: "2026-04-09T11:40:00Z",
      updated_at: "2026-04-09T11:43:00Z",
      result: {
        live_state: {
          current_stage: "review",
          current_step: "reviewer_draft",
          current_step_label: "Reviewer 审校正文",
          latest_agent_name: "Reviewer",
          latest_agent_summary: "正在收束情绪转折，避免角色突然失真。",
          stages: [
            { stage: "queued", label: "排队", status: "completed" },
            { stage: "context", label: "载入上下文", status: "completed" },
            { stage: "generate", label: "生成", status: "completed" },
            { stage: "review", label: "审校", status: "processing" },
            { stage: "persist", label: "回填", status: "pending" },
            { stage: "complete", label: "完成", status: "pending" },
          ],
        },
      },
    },
    {
      id: 9000,
      project_id: 101,
      chapter_id: 1001,
      scene_id: null,
      job_type: "outline",
      status: "completed",
      progress: 100,
      status_message: "Planner 已完成章节节奏规划。",
      error_message: "",
      created_at: "2026-04-09T11:10:00Z",
      updated_at: "2026-04-09T11:15:00Z",
      result: {
        live_state: {
          current_stage: "complete",
          current_step: "complete",
          current_step_label: "工作流完成",
          latest_agent_name: "Planner",
          latest_agent_summary: "十章结构已回填，节奏偏短剧化。",
          stages: [
            { stage: "queued", label: "排队", status: "completed" },
            { stage: "context", label: "载入上下文", status: "completed" },
            { stage: "generate", label: "生成", status: "completed" },
            { stage: "persist", label: "回填", status: "completed" },
            { stage: "complete", label: "完成", status: "completed" },
          ],
        },
      },
    },
    {
      id: 8999,
      project_id: 101,
      chapter_id: 1005,
      scene_id: null,
      job_type: "chapter_scenes",
      status: "awaiting_user",
      progress: 74,
      status_message: "Reviewer 建议你先确认第五章是否需要重写高潮段。",
      error_message: "",
      created_at: "2026-04-09T10:55:00Z",
      updated_at: "2026-04-09T11:05:00Z",
      result: {
        live_state: {
          current_stage: "review",
          current_step: "create_intervention",
          current_step_label: "等待作者确认",
          latest_agent_name: "Reviewer",
          latest_agent_summary: "本章冲突推进方向存在偏差，建议你先做决策。",
          stages: [
            { stage: "queued", label: "排队", status: "completed" },
            { stage: "context", label: "载入上下文", status: "completed" },
            { stage: "generate", label: "生成", status: "completed" },
            { stage: "review", label: "审校", status: "awaiting_user" },
            { stage: "persist", label: "回填", status: "pending" },
            { stage: "complete", label: "完成", status: "pending" },
          ],
        },
      },
    },
  ];

  const exports = [
    {
      id: 6001,
      status: "completed",
      formats: ["pdf", "docx"],
      files: [
        { format: "pdf", url: "#review-pdf", download_url: "#review-pdf", quality_check: { status: "passed" } },
        { format: "docx", url: "#reading-docx", download_url: "#reading-docx", quality_check: { status: "passed" } },
      ],
      created_at: "2026-04-09T11:20:00Z",
      updated_at: "2026-04-09T11:24:00Z",
    },
  ];

  return {
    summary: {
      id: 101,
      title: "回声在凌晨四点",
      genre: "都市悬疑",
      tone: "克制、电影感、浅色纸页质感",
      era: "当代",
      target_chapter_count: 10,
      target_length: "10 章，短剧节奏",
      logline: "深夜电台主播在一次失控直播后，和调查记者一起撬开一桩旧案。",
      status: "drafting",
      cover_image_url: svgDataUri("项目封面", 34),
    },
    detail: {
      id: 101,
      title: "回声在凌晨四点",
      genre: "都市悬疑",
      tone: "克制、电影感、浅色纸页质感",
      era: "当代",
      target_chapter_count: 10,
      target_length: "10 章，短剧节奏",
      logline: "深夜电台主播在一次失控直播后，和调查记者一起撬开一桩旧案。",
      status: "drafting",
      cover_image_url: svgDataUri("项目封面", 34),
      story_bible: {
        world_notes: "故事发生在一座仍保留老电台系统的沿江城市，公开叙事和私密记忆长期错位。",
        style_notes: "浅色、克制、电影感，不靠堆砌辞藻取胜。",
        writing_rules: ["人物驱动剧情", "每章末尾保留钩子", "优先场景化和可视化动作"],
        addressing_rules: "林见川对沈昭在公众场合保持全名称呼，私下情绪上升时才会改口。",
        timeline_rules: "默认连续时间推进，不允许无提示跳时。",
      },
      chapters,
      characters: libraryCharacters.filter((item) => item.linked_project_ids.includes(101)),
      jobs,
      exports,
    },
    characterLibrary: libraryCharacters,
    storyBibleRevisions: [
      { id: 3202, revision_index: 3, created_by: "user", summary: "补充了称呼规则和时间线约束。" },
      { id: 3201, revision_index: 2, created_by: "agent", summary: "Planner 基于项目设定丰富世界观约束。" },
      { id: 3200, revision_index: 1, created_by: "system", summary: "系统初始化 Story Bible。" },
    ],
    chapterRevisions: {
      1003: [
        {
          id: 7003,
          summary: "Writer 初稿经 Reviewer 修订后回填。",
          created_by: "agent",
          revision_kind: "reviewer_apply",
          narrative_block_count: 3,
          scene_count: 2,
        },
        {
          id: 7002,
          summary: "用户微调第二段节奏。",
          created_by: "user",
          revision_kind: "user_patch",
          narrative_block_count: 3,
          scene_count: 2,
        },
      ],
    },
    jobDetails: {
      9001: {
        id: 9001,
        project_id: 101,
        chapter_id: 1003,
        job_type: "chapter_draft",
        status: "processing",
        progress: 64,
        status_message: "Writer 已完成初稿，Reviewer 正在压口吻与时间线。",
        error_message: "",
        pending_interventions: [],
        result: {
          live_state: {
            current_stage: "review",
            current_step: "reviewer_draft",
            current_step_label: "Reviewer 审校正文",
            latest_agent_name: "Reviewer",
            latest_agent_summary: "正在收束情绪转折，避免角色突然失真。",
            stages: [
              { stage: "queued", label: "排队", status: "completed" },
              { stage: "context", label: "载入上下文", status: "completed" },
              { stage: "generate", label: "生成", status: "completed" },
              { stage: "review", label: "审校", status: "processing" },
              { stage: "persist", label: "回填", status: "pending" },
              { stage: "complete", label: "完成", status: "pending" },
            ],
          },
        },
        agent_runs: [
          {
            id: 1,
            step_key: "writer_draft",
            agent_name: "Writer",
            model_id: "gpt-4o-mini",
            status: "completed",
            adoption_state: "applied",
            input_summary: "读取项目基调、角色口吻、上一章钩子和当前章目标。",
            public_notes: [
              "先用环境和动作把人物拉进同一空间，再逐步抬高冲突。",
              "保留短剧式章尾钩子，但正文不写成硬模板。"
            ],
            prompt_preview: "聚焦广播楼夜景、压低情绪、把关系试探放进对白节拍里。",
            output_summary: "完成 3 段正文，末尾保留楼下有人抵达的动作钩子。",
            issues: [],
            decision: "",
            stream_text: "正在整理第三段情绪...\n补强沈昭进入走廊后的压迫感...\n把章尾收在门外车灯这一帧。",
            error_message: "",
            started_at: "2026-04-09T11:40:10Z",
            completed_at: "2026-04-09T11:41:48Z",
          },
          {
            id: 2,
            step_key: "reviewer_draft",
            agent_name: "Reviewer",
            model_id: "gpt-4o-mini",
            status: "processing",
            adoption_state: "proposed",
            input_summary: "检查角色口吻一致性、时间线提示和章尾钩子强度。",
            public_notes: [
              "林见川的情绪不能突然外放，需要继续压住。",
              "沈昭的动作要更精确，让两人的关系紧张但不直白。"
            ],
            prompt_preview: "重点审角色声线和信息揭示节奏，不公开隐藏推理。",
            output_summary: "已识别到 2 处需要轻修的口吻与信息节奏问题。",
            issues: ["第二段措辞略显外放。", "第三段信息揭示稍快。"],
            decision: "accept",
            stream_text: "比对角色口吻...\n检查时间线跳点...\n准备返回修订建议。",
            error_message: "",
            started_at: "2026-04-09T11:41:49Z",
            completed_at: "",
          },
        ],
      },
      9000: {
        id: 9000,
        project_id: 101,
        chapter_id: 1001,
        job_type: "outline",
        status: "completed",
        progress: 100,
        status_message: "Planner 已完成章节节奏规划。",
        error_message: "",
        pending_interventions: [],
        result: {
          live_state: {
            current_stage: "complete",
            current_step: "complete",
            current_step_label: "工作流完成",
            latest_agent_name: "Planner",
            latest_agent_summary: "十章结构已回填，节奏偏短剧化。",
            stages: [
              { stage: "queued", label: "排队", status: "completed" },
              { stage: "context", label: "载入上下文", status: "completed" },
              { stage: "generate", label: "生成", status: "completed" },
              { stage: "persist", label: "回填", status: "completed" },
              { stage: "complete", label: "完成", status: "completed" },
            ],
          },
        },
        agent_runs: [
          {
            id: 3,
            step_key: "planner",
            agent_name: "Planner",
            model_id: "gpt-4o-mini",
            status: "completed",
            adoption_state: "applied",
            input_summary: "读取作品设定、角色卡与目标章节数。",
            public_notes: ["优先短剧节奏，每章尾部都留下小钩子。"],
            prompt_preview: "围绕直播事故和人物试探设计十章结构。",
            output_summary: "输出十章大纲，并补强 Story Bible 的称呼与时间线规则。",
            issues: [],
            decision: "",
            stream_text: "",
            error_message: "",
            started_at: "2026-04-09T11:10:12Z",
            completed_at: "2026-04-09T11:12:55Z",
          },
        ],
      },
      8999: {
        id: 8999,
        project_id: 101,
        chapter_id: 1005,
        job_type: "chapter_scenes",
        status: "awaiting_user",
        progress: 74,
        status_message: "Reviewer 建议你先确认第五章是否需要重写高潮段。",
        error_message: "",
        pending_interventions: [
          {
            id: 8805,
            chapter_id: 1005,
            intervention_type: "rewrite_writer",
            reviewer_notes: "第五章高潮段的人物主动性不够，建议重写。",
            suggested_guidance: "把沈昭的行动动机前置，避免像被剧情推着走。",
            user_guidance: "",
            status: "pending",
          },
        ],
        result: {
          live_state: {
            current_stage: "review",
            current_step: "create_intervention",
            current_step_label: "等待作者确认",
            latest_agent_name: "Reviewer",
            latest_agent_summary: "本章冲突推进方向存在偏差，建议你先做决策。",
            stages: [
              { stage: "queued", label: "排队", status: "completed" },
              { stage: "context", label: "载入上下文", status: "completed" },
              { stage: "generate", label: "生成", status: "completed" },
              { stage: "review", label: "审校", status: "awaiting_user" },
              { stage: "persist", label: "回填", status: "pending" },
              { stage: "complete", label: "完成", status: "pending" },
            ],
          },
        },
        agent_runs: [
          {
            id: 4,
            step_key: "reviewer_scenes",
            agent_name: "Reviewer",
            model_id: "gpt-4o-mini",
            status: "completed",
            adoption_state: "proposed",
            input_summary: "检查第五章场景冲突与人物主动性。",
            public_notes: ["这一章的冲突点够强，但人物决定太被动，会削弱代入感。"],
            prompt_preview: "只暴露可协作摘要，不暴露隐藏推理。",
            output_summary: "建议作者确认是否重写高潮段。",
            issues: ["高潮段缺少角色主动决策。"],
            decision: "rewrite_writer",
            stream_text: "",
            error_message: "",
            started_at: "2026-04-09T11:03:00Z",
            completed_at: "2026-04-09T11:05:00Z",
          },
        ],
      },
    },
  };
}

async function installWorkspaceRoutes(page, fixture) {
  await page.route("**/api/projects", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([fixture.summary]),
    });
  });

  await page.route("**/api/characters", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(fixture.characterLibrary),
    });
  });

  await page.route("**/api/projects/101/story-bible/revisions", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(fixture.storyBibleRevisions),
    });
  });

  await page.route("**/api/projects/101", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(fixture.detail),
    });
  });

  await page.route(/.*\/api\/chapters\/(\d+)\/revisions$/, async (route) => {
    const chapterId = Number(route.request().url().match(/\/api\/chapters\/(\d+)\/revisions$/)?.[1] || 0);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(fixture.chapterRevisions[chapterId] || []),
    });
  });

  await page.route(/.*\/api\/jobs\/(\d+)$/, async (route) => {
    const jobId = Number(route.request().url().match(/\/api\/jobs\/(\d+)$/)?.[1] || 0);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(fixture.jobDetails[jobId] || fixture.jobDetails[9001]),
    });
  });

  await page.route(/.*\/api\/jobs\/(\d+)\/stream$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: "event: done\ndata: {}\n\n",
    });
  });
}

async function bootstrapWorkspace(page, fixture) {
  await page.addInitScript(({ user }) => {
    localStorage.setItem("storycraft_token", "playwright-token");
    localStorage.setItem("storycraft_user", JSON.stringify(user));
  }, { user: { id: 501, email: "playwright@example.com", pen_name: "验收作者" } });

  await installWorkspaceRoutes(page, fixture);
  await page.goto("/studio/#/projects/101");
  await expect(page.getByText("《回声在凌晨四点》工作空间")).toBeVisible();
  await expect(page.locator(".workspace-grid")).toBeVisible();
}

async function collectLayoutMetrics(page) {
  return page.evaluate(() => {
    function pick(selector) {
      const element = document.querySelector(selector);
      if (!element) {
        return null;
      }
      const rect = element.getBoundingClientRect();
      return {
        selector,
        top: rect.top,
        left: rect.left,
        right: rect.right,
        bottom: rect.bottom,
        width: rect.width,
        height: rect.height,
        scrollHeight: element.scrollHeight,
        clientHeight: element.clientHeight,
        scrollWidth: element.scrollWidth,
        clientWidth: element.clientWidth,
        overflowY: window.getComputedStyle(element).overflowY,
        overflowX: window.getComputedStyle(element).overflowX,
      };
    }

    return {
      layoutMode: document.querySelector("#projectWorkspace")?.dataset.layoutMode || "",
      density: document.querySelector("#projectWorkspace")?.dataset.density || "",
      workspaceGrid: pick(".workspace-grid"),
      assetColumn: pick(".asset-column"),
      storyBiblePanel: pick(".story-bible-panel"),
      storyBibleSummaryCard: pick(".story-bible-summary-card"),
      assetPanel: pick(".asset-panel"),
      storyColumn: pick(".story-column"),
      railColumn: pick(".rail-column"),
      chapterTabs: pick(".chapter-tabs"),
      chapterDetail: pick(".chapter-detail"),
      agentPanel: pick(".agent-panel"),
      assetScrollRegion: pick(".asset-scroll-region"),
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight,
      },
    };
  });
}

async function assertNoHorizontalOverlap(metrics) {
  const asset = metrics.assetColumn;
  const story = metrics.storyColumn;
  const rail = metrics.railColumn;
  expect(asset).toBeTruthy();
  expect(story).toBeTruthy();
  expect(rail).toBeTruthy();
  expect(asset.right).toBeLessThanOrEqual(story.left + 2);
  expect(story.right).toBeLessThanOrEqual(rail.left + 2);
}

async function assertLeftRailDoesNotOverflow(metrics) {
  expect(metrics.assetColumn).toBeTruthy();
  expect(metrics.storyBiblePanel).toBeTruthy();
  expect(metrics.storyBibleSummaryCard).toBeTruthy();
  expect(metrics.assetPanel).toBeTruthy();
  expect(metrics.assetColumn.scrollHeight).toBeLessThanOrEqual(metrics.assetColumn.clientHeight + 2);
  expect(metrics.storyBibleSummaryCard.bottom).toBeLessThanOrEqual(metrics.storyBiblePanel.bottom + 2);
  expect(metrics.storyBiblePanel.bottom).toBeLessThanOrEqual(metrics.assetPanel.top - 8);
}

test.describe("workspace acceptance", () => {
  const fixture = buildProjectFixture();

  test("captures wide desktop workspace", async ({ page }) => {
    await page.setViewportSize({ width: 1680, height: 1080 });
    await bootstrapWorkspace(page, fixture);

    await page.getByRole("button", { name: /展开轨迹/ }).click();
    await page.locator('.chapter-tabs [data-select-chapter="1003"]').click();
    await page.waitForTimeout(250);

    const metrics = await collectLayoutMetrics(page);
    await assertNoHorizontalOverlap(metrics);
    await assertLeftRailDoesNotOverflow(metrics);
    expect(metrics.layoutMode).toBe("wide");
    expect(metrics.chapterDetail.scrollHeight).toBeGreaterThan(metrics.chapterDetail.clientHeight);
    expect(metrics.agentPanel.scrollHeight).toBeGreaterThan(metrics.agentPanel.clientHeight);
    expect(metrics.assetScrollRegion.scrollHeight).toBeGreaterThan(metrics.assetScrollRegion.clientHeight);

    await page.screenshot({
      path: "test-results/workspace-wide.png",
      fullPage: true,
    });

    console.log("workspace-wide metrics", JSON.stringify(metrics, null, 2));
  });

  test("captures balanced laptop workspace", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 940 });
    await bootstrapWorkspace(page, fixture);

    await page.getByRole("button", { name: /展开轨迹/ }).click();
    await page.waitForTimeout(250);

    const metrics = await collectLayoutMetrics(page);
    await assertNoHorizontalOverlap(metrics);
    await assertLeftRailDoesNotOverflow(metrics);
    expect(metrics.layoutMode).toBe("balanced");
    expect(metrics.chapterTabs.scrollWidth).toBeGreaterThan(metrics.chapterTabs.clientWidth);
    expect(metrics.chapterDetail.scrollHeight).toBeGreaterThan(metrics.chapterDetail.clientHeight);

    await page.screenshot({
      path: "test-results/workspace-balanced.png",
      fullPage: true,
    });

    console.log("workspace-balanced metrics", JSON.stringify(metrics, null, 2));
  });

  test("opens story bible detail modal from the compact rail card", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 940 });
    await bootstrapWorkspace(page, fixture);

    await page.getByRole("button", { name: "设定详情" }).click();

    const modal = page.locator("#storyBibleModal");
    await expect(modal).toBeVisible();
    await expect(modal.getByRole("button", { name: "保存设定版本" })).toBeVisible();
    await expect(modal.getByText("世界观", { exact: true })).toBeVisible();
    await expect(modal.getByText("最近设定版本")).toBeVisible();
  });
});
