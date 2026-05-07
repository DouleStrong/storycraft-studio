const DEMO_MODE_VALUES = new Set(["1", "true", "showcase", "demo"]);

function cloneDemoData(value) {
  return JSON.parse(JSON.stringify(value));
}

function buildSvgDataUrl({ title, subtitle, accent, detail = "" }) {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" viewBox="0 0 1200 720">
      <defs>
        <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#1a2238" />
          <stop offset="55%" stop-color="#20365b" />
          <stop offset="100%" stop-color="${accent}" />
        </linearGradient>
        <linearGradient id="shine" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stop-color="rgba(255,255,255,0.05)" />
          <stop offset="100%" stop-color="rgba(255,255,255,0.24)" />
        </linearGradient>
      </defs>
      <rect width="1200" height="720" rx="36" fill="url(#bg)" />
      <circle cx="980" cy="160" r="120" fill="rgba(255,255,255,0.1)" />
      <circle cx="1030" cy="130" r="52" fill="rgba(255,255,255,0.18)" />
      <rect x="72" y="88" width="1056" height="544" rx="28" fill="rgba(8,12,24,0.26)" stroke="url(#shine)" />
      <text x="96" y="166" fill="#F8F3E8" font-size="24" font-family="Segoe UI, Microsoft YaHei, sans-serif">${subtitle}</text>
      <text x="96" y="258" fill="#FFFFFF" font-size="62" font-weight="700" font-family="Segoe UI, Microsoft YaHei, sans-serif">${title}</text>
      <text x="96" y="332" fill="#DCE8FF" font-size="28" font-family="Segoe UI, Microsoft YaHei, sans-serif">${detail}</text>
      <rect x="96" y="410" width="250" height="12" rx="6" fill="rgba(255,255,255,0.2)" />
      <rect x="96" y="450" width="420" height="12" rx="6" fill="rgba(255,255,255,0.14)" />
      <rect x="96" y="490" width="340" height="12" rx="6" fill="rgba(255,255,255,0.14)" />
      <rect x="96" y="560" width="210" height="52" rx="18" fill="rgba(255,255,255,0.14)" stroke="rgba(255,255,255,0.2)" />
      <text x="126" y="594" fill="#FFFFFF" font-size="22" font-family="Segoe UI, Microsoft YaHei, sans-serif">StoryCraft Demo</text>
    </svg>
  `;
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

function buildDownloadData(label) {
  return `data:text/plain;charset=UTF-8,${encodeURIComponent(label)}`;
}

function findStoryBibleDiff(session, projectId, revisionId) {
  return session.storyBibleDiffsByProjectId[String(projectId)]?.[String(revisionId)] || null;
}

function findChapterDiff(session, chapterId, revisionId) {
  return session.chapterRevisionDiffsByChapterId[String(chapterId)]?.[String(revisionId)] || null;
}

function buildDemoProjectAssets() {
  return {
    cover: buildSvgDataUrl({
      title: "魔法学院伙伴 Demo",
      subtitle: "NPC 对话生产后台",
      accent: "#7F6AF7",
      detail: "洛克王国：世界风格的校园探索与精灵陪伴剧情",
    }),
    mentor: buildSvgDataUrl({
      title: "薇岚导师",
      subtitle: "学院引导者",
      accent: "#E2A74B",
      detail: "稳重、温柔、能把复杂任务拆成可执行步骤",
    }),
    sprite: buildSvgDataUrl({
      title: "霁光",
      subtitle: "精灵伙伴",
      accent: "#55C3A5",
      detail: "好奇、活泼，负责把世界观信息自然嵌入对话",
    }),
    rival: buildSvgDataUrl({
      title: "夜巡学员",
      subtitle: "竞争角色",
      accent: "#DB6D7D",
      detail: "表面冷淡，实际推动玩家成长与主线悬念",
    }),
    sceneGate: buildSvgDataUrl({
      title: "晨雾校门",
      subtitle: "Scene 1",
      accent: "#7CC6F6",
      detail: "入学引导、身份识别、第一轮 NPC 触达",
    }),
    sceneDorm: buildSvgDataUrl({
      title: "湖畔宿舍",
      subtitle: "Scene 2",
      accent: "#72A97E",
      detail: "伙伴养成、安抚反馈、关系深化",
    }),
    sceneForest: buildSvgDataUrl({
      title: "夜色试炼林",
      subtitle: "Scene 3",
      accent: "#8B6CF0",
      detail: "任务冲突、线索复核、悬念回收",
    }),
  };
}

export function isDemoModeEnabled(source = "") {
  const raw = String(source || "");
  const searchParams = raw.startsWith("?")
    ? new URLSearchParams(raw)
    : new URL(raw || "https://demo.local/", "https://demo.local/").searchParams;
  return DEMO_MODE_VALUES.has(String(searchParams.get("demo") || "").trim().toLowerCase());
}

export function getDemoBannerLabel() {
  return "Demo 展示版";
}

export function getDemoReadOnlyMessage() {
  return "当前为 Demo 展示版，已保留展示流程，暂未接入真实后端。";
}

export function resolveDemoInitialView(session) {
  return session?.currentProject ? "workspace" : "dashboard";
}

export function resolveDemoInitialRoute(session) {
  if (session?.currentProject && session?.currentProjectId) {
    return {
      view: "workspace",
      projectId: session.currentProjectId,
    };
  }
  return {
    view: "dashboard",
    projectId: null,
  };
}

export function buildDemoSession() {
  const assets = buildDemoProjectAssets();
  const projectId = 501;
  const chapterOneId = 6101;
  const chapterTwoId = 6102;
  const chapterThreeId = 6103;
  const storyBibleRevisionId = 7202;
  const chapterRevisionId = 8102;
  const exportId = 8301;
  const focusJobId = 9102;

  const characterLibrary = [
    {
      id: 101,
      name: "薇岚导师",
      role: "主线导师 / 新手引导 NPC",
      personality: "耐心、冷静、擅长把信息分层解释",
      goal: "帮助新生完成入学试炼并建立对学院的信任感",
      speech_style: "语气温和，句子短，常以提问引导玩家选择",
      appearance: "银蓝色长袍，肩部有星纹徽记，手持折光法杖",
      relationships: "与霁光是长期搭档，对夜巡学员保持观察",
      status: "可互动",
      relationship: "师生关系",
      relationshipLevel: 45,
      currentMood: "平静而专注",
      memoryTags: ["记得你的第一次提问", "关注你的成长", "理解你的困惑"],
      signature_line: "先别急着回答，先看清你想保护的是什么。",
      npc_dialogue_profile: {
        need_signal: "她会先确认玩家是否理解试炼规则，而不是直接给标准答案。",
        relationship_hook: "回答能体现耐心、观察力和保护意图时，好感更容易上升。",
        friendship_stage: "可结交：导师信任度 45%",
        opening_line: "新生，我不会替你决定路线。你先说说，刚才徽石的回响更像提醒、邀请，还是警告？",
        smart_replies: [
          "我想先确认徽石是不是在求救。",
          "如果我选错，你会怎么提醒我？",
          "我可以把试炼规则复述给你听。",
          "我更想保护同行的伙伴。",
        ],
        reaction_samples: [
          {
            trigger: "规则理解",
            response: "你没有急着往前冲，这很好。能把规则听进去的人，才有资格改变规则。",
            affection_delta: "+8 信任",
          },
          {
            trigger: "保护伙伴",
            response: "把伙伴放在选择里，是我愿意继续带你的理由。今晚的第二道门，我会替你留意。",
            affection_delta: "+12 好感",
          },
        ],
      },
      visual_profile: {
        visual_anchor: "银蓝长袍 | 星纹徽记 | 折光法杖 | 稳定目光",
      },
      reference_images: [{ url: assets.mentor }],
      linked_project_ids: [projectId],
    },
    {
      id: 102,
      name: "霁光",
      role: "精灵伙伴 / 情绪反馈 NPC",
      personality: "活泼、敏锐、会主动提醒玩家注意隐藏线索",
      goal: "陪伴玩家完成探索，让世界观信息通过互动自然露出",
      speech_style: "表达轻快，偏口语，擅长用比喻解释复杂概念",
      appearance: "薄荷色翅翼，尾部带金色微光，动作轻巧",
      relationships: "信任薇岚导师，对玩家有高好感起点",
      status: "陪伴中",
      relationship: "亲密伙伴",
      relationshipLevel: 72,
      currentMood: "兴奋而期待",
      memoryTags: ["想和你继续探索", "会主动提醒隐藏线索", "把你当成优先同行者"],
      signature_line: "你先往前走，我会把风里的声音都记下来。",
      npc_dialogue_profile: {
        need_signal: "它喜欢被玩家认真回应，也会把隐藏线索包装成轻快提醒。",
        relationship_hook: "玩家愿意分享感受、约定下次行动或回应它的陪伴时，亲密度上升。",
        friendship_stage: "可结交：伙伴亲密度 72%",
        opening_line: "你终于来啦！我刚刚听见风里有三种声音，一种像铃，一种像水，还有一种像有人在忍住不说话。你想先追哪一种？",
        smart_replies: [
          "先追像铃的声音。",
          "你害怕的时候会躲起来吗？",
          "下次探索我想带你一起去。",
          "把你听见的线索都告诉我。",
        ],
        reaction_samples: [
          {
            trigger: "陪伴承诺",
            response: "说好了哦！那我会把最亮的尾光留给你，免得你在雾里找不到路。",
            affection_delta: "+10 亲密",
          },
          {
            trigger: "线索追问",
            response: "嘿，你抓到重点了。像铃的声音来自校门背面，不是危险，是有人想让你回头。",
            affection_delta: "+6 好感",
          },
        ],
      },
      visual_profile: {
        visual_anchor: "薄荷色翅翼 | 金色尾光 | 浮空移动 | 高敏捷感",
      },
      reference_images: [{ url: assets.sprite }],
      linked_project_ids: [projectId],
    },
    {
      id: 103,
      name: "夜巡学员",
      role: "竞争者 / 悬念推动 NPC",
      personality: "克制、警惕、发言少但信息密度高",
      goal: "测试玩家判断力，并把试炼线索导向第二章冲突",
      speech_style: "句式简洁，留白多，常用反问制造压力",
      appearance: "深紫色短斗篷，夜巡徽章别在袖口，目光锐利",
      relationships: "与学院守夜队关系紧密，对导师体系保持质疑",
      status: "谨慎观察",
      relationship: "警惕中的合作对象",
      relationshipLevel: 28,
      currentMood: "克制且戒备",
      memoryTags: ["会记住你的判断失误", "只认可清晰证据", "对真诚反问有反应"],
      signature_line: "如果你连最轻的谎言都听不出来，今晚就别进林子。",
      npc_dialogue_profile: {
        need_signal: "他用质疑测试玩家判断力，讨厌空泛讨好，更认可清晰证据。",
        relationship_hook: "玩家能指出线索、承认不确定或反问他的动机时，会从警惕转为认可。",
        friendship_stage: "待结交：警惕度 68%",
        opening_line: "别急着解释。你只要回答我一件事：结界裂缝旁边的脚印，是逃走的人留下的，还是故意引你过去的？",
        smart_replies: [
          "像是故意引我过去的。",
          "我需要再看一眼脚印方向。",
          "你为什么这么在意我的判断？",
          "如果我判断错了，你会拦我吗？",
        ],
        reaction_samples: [
          {
            trigger: "证据判断",
            response: "还算清醒。脚印太整齐，真正逃命的人不会这样走。你可以跟上，但别拖慢我。",
            affection_delta: "+7 认可",
          },
          {
            trigger: "反问动机",
            response: "敢反问，比急着讨好强。记住这点，夜巡队不收只会点头的人。",
            affection_delta: "+5 尊重",
          },
        ],
      },
      visual_profile: {
        visual_anchor: "深紫短斗篷 | 夜巡徽章 | 冷峻目光 | 留白式表达",
      },
      reference_images: [{ url: assets.rival }],
      linked_project_ids: [],
    },
  ];

  const exportBundle = {
    id: exportId,
    status: "completed",
    formats: ["pdf", "docx"],
    created_at: "2026-05-05T13:10:00.000Z",
    completed_at: "2026-05-05T13:18:00.000Z",
    delivery_summary: {
      quality_status: "passed",
      chapter_count: 3,
      character_count: 2,
      illustration_count: 3,
      total_size_bytes: 2485760,
      total_page_count: 26,
    },
    files: [
      {
        format: "pdf",
        url: buildDownloadData("StoryCraft Demo PDF 占位文件"),
        page_count: 26,
      },
      {
        format: "docx",
        url: buildDownloadData("StoryCraft Demo DOCX 占位文件"),
      },
    ],
  };

  const focusJob = {
    id: focusJobId,
    job_type: "chapter_scenes",
    status: "awaiting_user",
    progress: 100,
    project_id: projectId,
    chapter_id: chapterOneId,
    created_at: "2026-05-05T12:20:00.000Z",
    updated_at: "2026-05-05T12:31:00.000Z",
    completed_at: "2026-05-05T12:31:00.000Z",
    status_message: "Reviewer 建议收紧第一轮引导话术，让玩家更快感知试炼风险。",
    pending_interventions: [
      {
        id: 301,
        status: "pending",
        intervention_type: "rewrite_writer",
        reviewer_notes: "开场两段说明偏长，玩家在第一分钟拿不到可互动目标。",
        suggested_guidance: "保留世界观信息，但把“学院守则”改成导师追问，用一问一答带出试炼规则。",
      },
    ],
    result: {
      live_state: {
        current_stage: "review",
        current_step: "review_feedback",
        current_step_label: "Reviewer 回合：要求收紧入学引导",
        latest_agent_summary: "已定位到 Scene 1 前两段说明过载，建议改为导师与精灵的短对话配合。",
        stage_history: [
          { stage: "queued", status: "completed" },
          { stage: "context", status: "completed" },
          { stage: "generate", status: "completed" },
          { stage: "review", status: "completed" },
        ],
      },
    },
    agent_runs: [
      {
        id: 401,
        step_key: "context",
        agent_name: "World Analyst",
        model_id: "gpt-5.5",
        status: "completed",
        adoption_state: "accepted",
        input_summary: "读取项目 Story Bible、角色设定和第一章目标。",
        public_notes: ["确认玩家在 90 秒内需要遇到导师和精灵两个关键 NPC。"],
        output_summary: "补齐入学试炼的目标链路，建议将守则信息拆成三个触发点。",
      },
      {
        id: 402,
        step_key: "generate",
        agent_name: "Scene Planner",
        model_id: "gpt-5.5",
        status: "completed",
        adoption_state: "accepted",
        input_summary: "围绕第一章生成 Scene 拆分与对话节奏。",
        public_notes: ["生成 3 个 Scene 候选，其中 Scene 1 过长。"],
        output_summary: "已完成章节分镜，玩家 4 分钟内可完成首次试炼分支。",
      },
      {
        id: 403,
        step_key: "review",
        agent_name: "Narrative Reviewer",
        model_id: "gpt-5.5",
        status: "completed",
        adoption_state: "needs_revision",
        decision: "awaiting_user",
        input_summary: "检查首章引导节奏、信息密度与 NPC 分工。",
        public_notes: ["发现首屏信息灌输偏重，建议压缩文案并提升互动频率。"],
        output_summary: "保留世界观亮点，重写导师首段发言，减少连续说明。",
      },
    ],
  };

  const completedOutlineJob = {
    id: 9101,
    job_type: "outline",
    status: "completed",
    progress: 100,
    project_id: projectId,
    created_at: "2026-05-05T10:05:00.000Z",
    updated_at: "2026-05-05T10:22:00.000Z",
    completed_at: "2026-05-05T10:22:00.000Z",
    result: {
      live_state: {
        current_stage: "complete",
        current_step: "outline_done",
        current_step_label: "剧情大纲已完成",
        latest_agent_summary: "已输出 3 章主线、2 条伙伴支线和 1 条夜巡悬念线。",
        stage_history: [
          { stage: "queued", status: "completed" },
          { stage: "context", status: "completed" },
          { stage: "generate", status: "completed" },
        ],
      },
    },
  };

  const completedExportJob = {
    id: 9103,
    job_type: "export",
    status: "completed",
    progress: 100,
    project_id: projectId,
    created_at: "2026-05-05T13:10:00.000Z",
    updated_at: "2026-05-05T13:18:00.000Z",
    completed_at: "2026-05-05T13:18:00.000Z",
    result: {
      export_id: exportId,
      live_state: {
        current_stage: "complete",
        current_step: "export_done",
        current_step_label: "导出完成",
        latest_agent_summary: "PDF 与 DOCX 已通过交付质检，可用于策划评审与配音同步。",
        stage_history: [
          { stage: "queued", status: "completed" },
          { stage: "generate", status: "completed" },
          { stage: "complete", status: "completed" },
        ],
      },
    },
  };

  const chapters = [
    {
      id: chapterOneId,
      order_index: 1,
      title: "入学雾门",
      status: "needs_regeneration",
      summary: "玩家第一次进入学院，与导师和精灵伙伴相遇，并触发夜巡学员的质疑。",
      chapter_goal: "让玩家理解试炼目标，并在 4 分钟内做出第一轮选择。",
      hook: "学院门外的徽石突然失灵，只有玩家能听见其内部回响。",
      is_locked: false,
      continuity_notes: [
        "霁光需要在第一章内建立陪伴感，避免只作为工具型提示精灵。",
        "夜巡学员首次出场只给出试炼警告，不提前泄露第二章核心谜底。",
      ],
      pending_interventions: [
        {
          id: 301,
          status: "pending",
          intervention_type: "rewrite_writer",
          reviewer_notes: "首屏说明偏多，建议把守则改写成导师问答。",
          suggested_guidance: "强化玩家选择感，让导师用两轮追问暴露学院规则。",
        },
      ],
      latest_revision: {
        id: chapterRevisionId,
      },
      source_story_bible_revision_id: storyBibleRevisionId,
      narrative_blocks: [
        {
          id: 1101,
          order_index: 1,
          content: "晨雾压在学院石阶上，徽石的光却只在你脚边亮起，像在等一个迟到很久的人。",
          is_locked: true,
          is_user_edited: false,
          source_revision_id: chapterRevisionId,
        },
        {
          id: 1102,
          order_index: 2,
          content: "薇岚没有先报上学院规章，而是让你描述刚刚听见的声音，以此判断你是否真的被徽石选中。",
          is_locked: false,
          is_user_edited: true,
          source_revision_id: chapterRevisionId,
        },
      ],
      scenes: [
        {
          id: 2101,
          title: "晨雾校门",
          scene_type: "引导",
          location: "学院正门",
          time_of_day: "清晨",
          objective: "完成玩家入场、导师识别和世界观第一层露出。",
          emotional_tone: "神秘但友好",
          cast_names: ["薇岚导师", "霁光"],
          visual_prompt: "魔法学院石门、晨雾、银蓝导师、薄荷色精灵伙伴、温暖引导氛围",
          is_locked: false,
          is_user_edited: true,
          dialogue_blocks: [
            {
              id: 3101,
              speaker: "薇岚导师",
              parenthetical: "看向徽石",
              content: "别急着证明自己，先告诉我，你刚刚听见的那道声音像谁。",
              is_locked: false,
              is_user_edited: true,
              source_revision_id: chapterRevisionId,
            },
            {
              id: 3102,
              speaker: "霁光",
              parenthetical: "",
              content: "它不是在催你，它是在确认你会不会回头看我一眼。",
              is_locked: true,
              is_user_edited: false,
              source_revision_id: chapterRevisionId,
            },
          ],
          illustrations: [
            {
              id: 4101,
              candidate_index: 1,
              url: assets.sceneGate,
              thumbnail_url: assets.sceneGate,
              prompt_text: "晨雾中的学院正门，银蓝长袍导师与薄荷色精灵伙伴站在石阶前，温暖神秘",
              is_canonical: true,
            },
          ],
        },
        {
          id: 2102,
          title: "湖畔宿舍",
          scene_type: "陪伴",
          location: "新生宿舍外廊",
          time_of_day: "傍晚",
          objective: "通过伙伴安抚和轻任务降低玩家初次进入世界的压力。",
          emotional_tone: "放松、亲近",
          cast_names: ["霁光"],
          visual_prompt: "湖畔宿舍，柔和灯光，精灵伙伴悬停在行李箱旁，陪伴感强",
          is_locked: false,
          is_user_edited: false,
          dialogue_blocks: [
            {
              id: 3103,
              speaker: "霁光",
              parenthetical: "绕着行李飞一圈",
              content: "你把最重要的东西放在哪一层，我就先守哪一层。",
              is_locked: false,
              is_user_edited: false,
              source_revision_id: chapterRevisionId,
            },
          ],
          illustrations: [
            {
              id: 4102,
              candidate_index: 1,
              url: assets.sceneDorm,
              thumbnail_url: assets.sceneDorm,
              prompt_text: "湖畔宿舍走廊，行李箱边悬浮的精灵伙伴，柔和灯光，轻松陪伴",
              is_canonical: true,
            },
          ],
        },
      ],
    },
    {
      id: chapterTwoId,
      order_index: 2,
      title: "守夜徽记",
      status: "scenes_ready",
      summary: "夜巡学员引导玩家在巡夜试炼中做出第一次带风险的判断。",
      chapter_goal: "让玩家感受到学院阵营分歧，并建立对夜巡支线的兴趣。",
      hook: "守夜徽记在林边亮起，提示有异常生物越过了结界。",
      is_locked: false,
      continuity_notes: ["夜巡学员的怀疑需要带一点欣赏，不要写成纯对立。"],
      pending_interventions: [],
      latest_revision: {
        id: 8103,
      },
      source_story_bible_revision_id: storyBibleRevisionId,
      narrative_blocks: [
        {
          id: 1103,
          order_index: 1,
          content: "结界边缘的光像被什么轻轻撕开，夜巡徽章在黑暗里比白天更亮。",
          is_locked: false,
          is_user_edited: false,
          source_revision_id: 8103,
        },
      ],
      scenes: [
        {
          id: 2103,
          title: "夜色试炼林",
          scene_type: "冲突",
          location: "结界林地",
          time_of_day: "深夜",
          objective: "制造试炼压力，让玩家感知夜巡线的节奏差异。",
          emotional_tone: "紧张、克制",
          cast_names: ["夜巡学员", "薇岚导师"],
          visual_prompt: "夜色林地，徽记蓝光，竞争者站在前方，导师在后方观察",
          is_locked: true,
          is_user_edited: false,
          dialogue_blocks: [
            {
              id: 3104,
              speaker: "夜巡学员",
              parenthetical: "",
              content: "你要是连结界裂缝都分不清，就别急着当谁的特别学生。",
              is_locked: true,
              is_user_edited: false,
              source_revision_id: 8103,
            },
          ],
          illustrations: [
            {
              id: 4103,
              candidate_index: 1,
              url: assets.sceneForest,
              thumbnail_url: assets.sceneForest,
              prompt_text: "夜色试炼林，蓝紫色结界裂缝，冷峻竞争者，紧张氛围",
              is_canonical: true,
            },
          ],
        },
      ],
    },
    {
      id: chapterThreeId,
      order_index: 3,
      title: "回响试炼",
      status: "outline_ready",
      summary: "玩家开始把前两章收集的信息拼成完整试炼线索。",
      chapter_goal: "推动主线从“被引导”转向“主动判断”。",
      hook: "回响厅记录了每位学员第一次听见徽石的瞬间。",
      is_locked: false,
      continuity_notes: ["第三章以选择分支为主，暂不扩写完整对话。"],
      pending_interventions: [],
      latest_revision: null,
      source_story_bible_revision_id: storyBibleRevisionId,
      narrative_blocks: [],
      scenes: [],
    },
  ];

  const currentProject = {
    id: projectId,
    title: "魔法学院伙伴 Demo",
    genre: "轻奇幻 / 养成冒险",
    tone: "温暖、神秘、带轻冲突",
    era: "学院试炼季",
    target_chapter_count: 3,
    target_length: "3 章可试玩主线",
    logline: "面向校园探索 RPG 的剧情与 NPC 对话生产后台，用一个可展示的章节工作台串起大纲、Scene、对话、插图和导出。",
    status: "待 reviewer 二次确认",
    cover_image_url: assets.cover,
    story_bible: {
      world_notes: "学院把“被世界选中”设计成一场需要被证明的试炼，玩家不是天降主角，而是一个被多方观察的新人。",
      style_notes: "对白保持轻奇幻、轻口语，导师负责解释秩序，精灵负责情绪陪伴，竞争者负责施压与悬念。",
      writing_rules: [
        "单轮对话优先服务玩家选择，不连续灌输设定。",
        "精灵伙伴不替玩家决策，只做提醒与共情。",
        "导师口吻稳定，不突然煽情。",
      ],
      addressing_rules: "导师称呼玩家为“新生”或直接使用名字；精灵伙伴更口语化；夜巡学员尽量少用敬语。",
      timeline_rules: "第一章完成入场与试炼引导，第二章加冲突，第三章开始回收线索。",
      current_revision: {
        id: storyBibleRevisionId,
        revision_index: 2,
      },
    },
    characters: characterLibrary.filter((item) => item.linked_project_ids.includes(projectId)),
    chapters,
    jobs: [completedExportJob, focusJob, completedOutlineJob],
    exports: [exportBundle],
  };

  const storyBibleRevisions = [
    {
      id: storyBibleRevisionId,
      revision_index: 2,
      created_by: "demo_user",
      created_at: "2026-05-05T11:02:00.000Z",
    },
    {
      id: 7201,
      revision_index: 1,
      created_by: "demo_user",
      created_at: "2026-05-04T18:40:00.000Z",
    },
  ];

  const chapterRevisions = {
    [chapterOneId]: [
      {
        id: chapterRevisionId,
        created_by: "demo_user",
        summary: "把开场改成导师问答，压缩连续设定说明。",
        revision_kind: "scene_pass",
        narrative_block_count: 2,
        scene_count: 2,
      },
      {
        id: 8101,
        created_by: "system",
        summary: "第一版章节拆解，信息量偏大。",
        revision_kind: "draft",
        narrative_block_count: 3,
        scene_count: 2,
      },
    ],
    [chapterTwoId]: [
      {
        id: 8103,
        created_by: "demo_user",
        summary: "强化夜巡学员的对抗感与欣赏并存。",
        revision_kind: "scene_pass",
        narrative_block_count: 1,
        scene_count: 1,
      },
    ],
    [chapterThreeId]: [],
  };

  const session = {
    token: "demo-token",
    user: {
      id: 1,
      pen_name: "作品集访客",
      email: "demo@storycraft.local",
    },
    projects: [currentProject],
    characterLibrary,
    currentProjectId: projectId,
    currentProject,
    activeChapterId: chapterOneId,
    selectedJobId: focusJobId,
    selectedJobDetail: focusJob,
    exportNotice: {
      projectId,
      bundle: exportBundle,
    },
    featuredExportId: exportId,
    storyBibleRevisions,
    storyBibleDiffsByProjectId: {
      [projectId]: {
        [storyBibleRevisionId]: {
          base_revision: {
            revision_index: 1,
          },
          target_revision: {
            revision_index: 2,
          },
          summary: {
            changed_field_count: 3,
          },
          fields: [
            {
              label: "世界观说明",
              changed: true,
              base_excerpt: "强调玩家被选中的特殊性。",
              target_excerpt: "改成多方观察玩家，让成长更主动。",
              added: ["多方观察", "试炼证明"],
              removed: ["天降主角"],
            },
            {
              label: "对白风格",
              changed: true,
              base_excerpt: "导师段落偏长，说明性较重。",
              target_excerpt: "导师通过提问推动玩家表达，再给规则反馈。",
              added: ["提问式引导"],
              removed: ["长段说明"],
            },
            {
              label: "时间线",
              changed: true,
              base_excerpt: "第二章直接进入夜巡冲突。",
              target_excerpt: "先铺垫试炼风险，再引出夜巡线。",
              added: ["铺垫风险"],
              removed: [],
            },
          ],
        },
      },
    },
    chapterRevisionsByChapterId: chapterRevisions,
    chapterRevisionDiffsByChapterId: {
      [chapterOneId]: {
        [chapterRevisionId]: {
          base: {
            label: "Revision #8101",
          },
          target: {
            label: "Revision #8102",
          },
          overview: {
            narrative_blocks: {
              changed: 2,
              added: 1,
              removed: 1,
            },
            scenes: {
              changed: 1,
              added: 0,
              removed: 0,
            },
            meta_change_count: 2,
            dialogue_count_delta: 1,
          },
          meta_changes: [
            {
              label: "章节摘要",
              status: "changed",
              base_excerpt: "导师先介绍学院守则。",
              target_excerpt: "导师先确认玩家是否真的听见徽石回响。",
            },
          ],
          narrative_block_changes: [
            {
              order_index: 1,
              status: "changed",
              base_excerpt: "学院晨钟先响起，守则广播覆盖整个广场。",
              target_excerpt: "徽石在玩家脚边亮起，玩家先被异常感吸引。",
            },
            {
              order_index: 2,
              status: "changed",
              base_excerpt: "导师连续解释三条学院规定。",
              target_excerpt: "导师用问答方式确认玩家感知，再带出规则。",
            },
          ],
          scene_changes: [
            {
              order_index: 1,
              status: "changed",
              base_title: "学院广播",
              target_title: "晨雾校门",
              base_excerpt: "说明性场景偏多。",
              target_excerpt: "增加玩家与导师、精灵的即时互动。",
            },
          ],
        },
      },
      [chapterTwoId]: {},
      [chapterThreeId]: {},
    },
    exportsById: {
      [exportId]: exportBundle,
    },
    jobsById: {
      [completedOutlineJob.id]: completedOutlineJob,
      [focusJob.id]: focusJob,
      [completedExportJob.id]: completedExportJob,
    },
    projectsById: {
      [projectId]: currentProject,
    },
  };

  return cloneDemoData(session);
}

export function resolveDemoApiResponse(session, path, options = {}) {
  const method = String(options.method || "GET").trim().toUpperCase();
  if (method !== "GET") {
    throw new Error(getDemoReadOnlyMessage());
  }

  const pathname = new URL(String(path || "/"), "https://demo.local").pathname;

  if (pathname === "/api/projects") {
    return cloneDemoData(session.projects || []);
  }

  if (pathname === "/api/characters") {
    return cloneDemoData(session.characterLibrary || []);
  }

  if (pathname === "/api/exports") {
    return cloneDemoData(Object.values(session.exportsById || {}));
  }

  const projectMatch = pathname.match(/^\/api\/projects\/(\d+)$/);
  if (projectMatch) {
    const project = session.projectsById?.[projectMatch[1]];
    if (!project) {
      throw new Error("Demo 项目不存在。");
    }
    return cloneDemoData(project);
  }

  const jobMatch = pathname.match(/^\/api\/jobs\/(\d+)$/);
  if (jobMatch) {
    const job = session.jobsById?.[jobMatch[1]];
    if (!job) {
      throw new Error("Demo 任务不存在。");
    }
    return cloneDemoData(job);
  }

  const exportMatch = pathname.match(/^\/api\/exports\/(\d+)$/);
  if (exportMatch) {
    const bundle = session.exportsById?.[exportMatch[1]];
    if (!bundle) {
      throw new Error("Demo 导出记录不存在。");
    }
    return cloneDemoData(bundle);
  }

  const storyBibleRevisionMatch = pathname.match(/^\/api\/projects\/(\d+)\/story-bible\/revisions$/);
  if (storyBibleRevisionMatch) {
    const projectId = storyBibleRevisionMatch[1];
    const revisions = String(session.currentProjectId) === projectId ? session.storyBibleRevisions : [];
    return cloneDemoData(revisions || []);
  }

  const storyBibleDiffMatch = pathname.match(/^\/api\/projects\/(\d+)\/story-bible\/revisions\/(\d+)\/diff$/);
  if (storyBibleDiffMatch) {
    const diff = findStoryBibleDiff(session, storyBibleDiffMatch[1], storyBibleDiffMatch[2]);
    if (!diff) {
      throw new Error("Demo Story Bible diff 不存在。");
    }
    return cloneDemoData(diff);
  }

  const chapterRevisionMatch = pathname.match(/^\/api\/chapters\/(\d+)\/revisions$/);
  if (chapterRevisionMatch) {
    return cloneDemoData(session.chapterRevisionsByChapterId?.[chapterRevisionMatch[1]] || []);
  }

  const chapterDiffMatch = pathname.match(/^\/api\/chapters\/(\d+)\/revisions\/(\d+)\/diff$/);
  if (chapterDiffMatch) {
    const diff = findChapterDiff(session, chapterDiffMatch[1], chapterDiffMatch[2]);
    if (!diff) {
      throw new Error("Demo 章节 diff 不存在。");
    }
    return cloneDemoData(diff);
  }

  throw new Error(`Demo 模式暂未覆盖接口：${pathname}`);
}
