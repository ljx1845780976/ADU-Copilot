export type Lang = "en" | "zh";

export const t: Record<Lang, Record<string, string>> = {
  en: {
    // Navbar
    "nav.login": "Login / Register",
    "nav.credits": "credits",
    "nav.buyCredits": "Buy Credits",
    "nav.logout": "Logout",

    // Splash
    "splash.subtitle": "California ADU Compliance AI Audit — Upload, Audit, Remediate.",
    "splash.enter": "Get Started",

    // Auth Dialog
    "auth.title": "Welcome to ADU Copilot",
    "auth.desc": "Sign in to audit your ADU project.",
    "auth.login": "Login",
    "auth.register": "Register",
    "auth.email": "Email",
    "auth.password": "Password",
    "auth.signIn": "Sign In",
    "auth.createAccount": "Create Account",
    "auth.signingIn": "Signing in...",
    "auth.creating": "Creating account...",
    "auth.google": "Google",
    "auth.orContinue": "or continue with",
    "auth.checkEmail": "Account created! Check your email for the confirmation link.",

    // Upload Zone
    "upload.title": "1. Upload Project PDF",
    "upload.dropHint": "Drag & drop your PDF here",
    "upload.clickHint": "or click to browse (PDF only, max 5 MB recommended)",
    "upload.extracting": "Extracting data from",
    "upload.complete": "Extraction complete. Review parameters below.",
    "upload.failed": "Extraction Failed",
    "upload.tryAgain": "Try again",
    "upload.largeFile": "Large File Detected",
    "upload.largeFileHint": "This PDF has {pages} pages and is larger than 5 MB. Select the pages you need to speed up parsing.",
    "upload.pageCount": "{selected} of {total} pages selected",
    "upload.selectAll": "Select All",
    "upload.deselectAll": "Deselect All",
    "upload.cancel": "Cancel",
    "upload.parsePages": "Parse Selected Pages",
    "upload.reupload": "Upload another file",
    "upload.noText": "No readable text found in this PDF. The file may be scanned or image-based.",

    // Params Form
    "params.title": "2. Review & Confirm Parameters",
    "params.desc": "Review and edit extracted data before running the audit.",
    "params.showAdvanced": "Show Advanced",
    "params.hideAdvanced": "Hide Advanced",
    "params.auditBtn": "Start Audit (Consumes 30 Credits)",
    "params.yes": "Yes",
    "params.no": "No",
    "params.section.Project Info": "Project Info",
    "params.section.Lot": "Lot",
    "params.section.Basic": "Basic",
    "params.section.Dwelling": "Dwelling",
    "params.section.Setbacks": "Setbacks",
    "params.section.Location": "Location",
    "params.section.Interior": "Interior",
    "params.section.JADU": "JADU",
    "params.section.Other": "Other",

    // Field Labels
    "field.project_address": "Project Address",
    "field.apn": "APN",
    "field.lot_size_sqft": "Lot Size (sq ft)",
    "field.primary_dwelling_sqft": "Primary Dwelling (sq ft)",
    "field.adu_type": "ADU Type",
    "field.proposed_adu_sqft": "Proposed ADU (sq ft)",
    "field.rear_setback_ft": "Rear Setback (ft)",
    "field.side_setback_ft": "Side Setback (ft)",
    "field.front_setback_ft": "Front Setback (ft)",
    "field.proposed_height_ft": "Proposed Height (ft)",
    "field.is_near_transit": "Near Transit (½ mile)",
    "field.is_jadu_within_primary_dwelling": "JADU within Primary",
    "field.jadu_has_separate_entrance": "JADU Separate Entrance",
    "field.stories": "Stories",
    "field.separation_from_primary_ft": "Separation from Primary (ft)",
    "field.adu_bedroom_count": "Bedrooms",
    "field.primary_structure_height_ft": "Primary Height (ft)",
    "field.adu_permitting_track": "Permitting Track",
    "field.jadu_shares_sanitation_with_primary": "Shares Sanitation",
    "field.jadu_has_separate_bathroom": "Separate Bathroom",
    "field.jadu_interior_entrance_to_main": "Interior Entrance to Main",
    "field.owner_occupies_primary": "Owner Occupies Primary",
    "field.min_ceiling_height_ft": "Min Ceiling Height (ft)",
    "field.roof_type_notes": "Roof Type Notes",

    // Audit
    "audit.title": "3. Audit Results",
    "audit.pass": "Pass",
    "audit.fail": "Fail",
    "audit.passCount": "{n} Pass",
    "audit.failCount": "{n} Fail",
    "audit.radar": "Compliance Radar",
    "audit.radarDesc": "Visual overview of key compliance dimensions.",
    "audit.checklist": "Audit Checklist",
    "audit.checklistDesc": "Detailed pass/fail results per rule.",
    "audit.score": "Score",
    "audit.creditsLeft": "Credits remaining",
    "audit.loading": "Running compliance audit...",

    // Advise
    "advise.title": "4. Expert Advice",
    "advise.allPassed": "All Checks Passed",
    "advise.allPassedDesc": "Your ADU project complies with all checked state standards. No remediation advice needed.",
    "advise.aiAdvice": "AI Remediation Advice",
    "advise.adviceDesc": "Get professional guidance on fixing {n} failed rule(s).",
    "advise.unlock": "Unlock (Consumes 50 Credits)",
    "advise.unlockHint": "Unlock AI-powered remediation advice",
    "advise.generating": "Generating...",
    "advise.insufficient": "Insufficient credits ({n}/50). Please buy more credits.",

    // Hero
    "hero.title": "ADU Copilot AI",
    "hero.subtitle": "California ADU compliance audit tool for homeowners and architects. Upload your PDF, get instant code compliance analysis, and receive AI-powered remediation guidance.",
    "hero.step1title": "Upload & Extract",
    "hero.step1desc": "Upload your project PDF, AI extracts 20+ building parameters automatically.",
    "hero.step2title": "Compliance Audit",
    "hero.step2desc": "30 credits for radar chart + Pass/Fail checklist based on California HCD ADU Handbook.",
    "hero.step3title": "AI Remediation",
    "hero.step3desc": "50 credits to unlock AI-powered fix suggestions for every failed rule.",

    // Page
    "page.section1": "1. Upload Project PDF",
    "page.section2": "2. Review & Confirm Parameters",
    "page.section3": "3. Audit Results",
    "page.section4": "4. Expert Advice",

    // Toast
    "toast.loginRequired": "Login Required",
    "toast.pleaseLogin": "Please login to run the audit.",
    "toast.auditFailed": "Audit Failed",
    "toast.adviceFailed": "Advice Failed",

    // Language
    "audit.refLinks": "Official Reference Links",
    "audit.refStandardPlans": "LADBS Approved Standard Plans",
    "audit.refHandbook": "HCD ADU Handbook",
    "advise.exportMd": "Export as Markdown",

    "lang.label": "中文",
  },

  zh: {
    // Navbar
    "nav.login": "登录 / 注册",
    "nav.credits": "积分",
    "nav.buyCredits": "购买积分",
    "nav.logout": "退出",

    // Splash
    "splash.subtitle": "加州 ADU 合规 AI 审计 — 上传、审计、修复。",
    "splash.enter": "开始使用",

    // Auth Dialog
    "auth.title": "欢迎使用 ADU Copilot",
    "auth.desc": "登录以审核您的 ADU 项目。",
    "auth.login": "登录",
    "auth.register": "注册",
    "auth.email": "邮箱",
    "auth.password": "密码",
    "auth.signIn": "登录",
    "auth.createAccount": "创建账户",
    "auth.signingIn": "登录中...",
    "auth.creating": "创建账户中...",
    "auth.google": "Google 登录",
    "auth.orContinue": "或使用以下方式",
    "auth.checkEmail": "账户已创建！请检查邮箱中的确认链接。",

    // Upload Zone
    "upload.title": "1. 上传项目 PDF",
    "upload.dropHint": "拖拽 PDF 文件到此处",
    "upload.clickHint": "或点击浏览（仅支持 PDF，建议 < 5 MB）",
    "upload.extracting": "正在从以下文件提取数据",
    "upload.complete": "提取完成，请检查下方参数。",
    "upload.failed": "提取失败",
    "upload.tryAgain": "重试",
    "upload.largeFile": "检测到大文件",
    "upload.largeFileHint": "此 PDF 有 {pages} 页，大小超过 5 MB。请选择需要的页面以加快解析速度。",
    "upload.pageCount": "已选 {selected} / 共 {total} 页",
    "upload.selectAll": "全选",
    "upload.deselectAll": "取消全选",
    "upload.cancel": "取消",
    "upload.parsePages": "解析选中页面 ({n})",
    "upload.reupload": "上传另一个文件",
    "upload.noText": "此 PDF 中未找到可读文字，文件可能是扫描件或图片。",

    // Params Form
    "params.title": "2. 确认参数",
    "params.desc": "审核开始前请检查并修改提取的数据。",
    "params.showAdvanced": "显示高级选项",
    "params.hideAdvanced": "隐藏高级选项",
    "params.auditBtn": "开始审计（消耗 30 积分）",
    "params.yes": "是",
    "params.no": "否",
    "params.section.Project Info": "项目信息",
    "params.section.Lot": "地块",
    "params.section.Basic": "基础",
    "params.section.Dwelling": "主屋",
    "params.section.Setbacks": "退距",
    "params.section.Location": "位置",
    "params.section.Interior": "室内",
    "params.section.JADU": "JADU",
    "params.section.Other": "其他",

    // Field Labels
    "field.project_address": "项目地址",
    "field.apn": "地籍号",
    "field.lot_size_sqft": "地块面积（平方英尺）",
    "field.primary_dwelling_sqft": "主屋面积（平方英尺）",
    "field.adu_type": "ADU 类型",
    "field.proposed_adu_sqft": "拟建 ADU 面积（平方英尺）",
    "field.rear_setback_ft": "后退退距（英尺）",
    "field.side_setback_ft": "侧边退距（英尺）",
    "field.front_setback_ft": "前院退距（英尺）",
    "field.proposed_height_ft": "拟建高度（英尺）",
    "field.is_near_transit": "邻近公交（½ 英里）",
    "field.is_jadu_within_primary_dwelling": "JADU 在主屋内",
    "field.jadu_has_separate_entrance": "JADU 独立入口",
    "field.stories": "层数",
    "field.separation_from_primary_ft": "与主屋间距（英尺）",
    "field.adu_bedroom_count": "卧室数",
    "field.primary_structure_height_ft": "主屋高度（英尺）",
    "field.adu_permitting_track": "许可轨道",
    "field.jadu_shares_sanitation_with_primary": "与主屋共用卫生设施",
    "field.jadu_has_separate_bathroom": "独立卫生间",
    "field.jadu_interior_entrance_to_main": "通往主屋的内部入口",
    "field.owner_occupies_primary": "业主自住主屋",
    "field.min_ceiling_height_ft": "最低层高（英尺）",
    "field.roof_type_notes": "屋顶类型说明",

    // Audit
    "audit.title": "3. 审计结果",
    "audit.pass": "通过",
    "audit.fail": "未通过",
    "audit.passCount": "{n} 项通过",
    "audit.failCount": "{n} 项未通过",
    "audit.radar": "合规雷达图",
    "audit.radarDesc": "关键合规维度的可视化概览。",
    "audit.checklist": "审计清单",
    "audit.checklistDesc": "各项规则的详细通过/未通过结果。",
    "audit.score": "得分",
    "audit.creditsLeft": "剩余积分",
    "audit.loading": "正在进行合规审计...",

    // Advise
    "advise.title": "4. 专家建议",
    "advise.allPassed": "全部检查通过",
    "advise.allPassedDesc": "您的 ADU 项目符合所有已检查的州标准，无需修复建议。",
    "advise.aiAdvice": "AI 修复建议",
    "advise.adviceDesc": "获取 {n} 项未通过规则的专业修复指导。",
    "advise.unlock": "解锁（消耗 50 积分）",
    "advise.unlockHint": "解锁 AI 驱动的修复方案",
    "advise.generating": "生成中...",
    "advise.insufficient": "积分不足 ({n}/50)，请购买更多积分。",

    // Page
    "page.section1": "1. 上传项目 PDF",
    "page.section2": "2. 确认参数",
    "page.section3": "3. 审计结果",
    "page.section4": "4. 专家建议",

    // Toast
    "toast.loginRequired": "需要登录",
    "toast.pleaseLogin": "请先登录后再运行审计。",
    "toast.auditFailed": "审计失败",
    "toast.adviceFailed": "建议生成失败",

    "audit.refLinks": "官方参考链接",
    "audit.refStandardPlans": "LADBS 批准标准方案",
    "audit.refHandbook": "HCD ADU 手册",
    "advise.exportMd": "导出为 Markdown",

    // Hero
    "hero.title": "ADU Copilot AI",
    "hero.subtitle": "面向加州业主和建筑师的 ADU 合规性 AI 审计工具。上传 PDF，即时获取法规合规分析，并接收 AI 驱动的修复建议。",
    "hero.step1title": "上传与提取",
    "hero.step1desc": "上传项目 PDF，AI 自动提取 20+ 项建筑参数。",
    "hero.step2title": "合规审计",
    "hero.step2desc": "消耗 30 积分，基于加州 HCD ADU 手册生成雷达图与 Pass/Fail 清单。",
    "hero.step3title": "AI 修复建议",
    "hero.step3desc": "消耗 50 积分，解锁 AI 为每项不通过规则提供的专业修复方案。",

    // Language
    "lang.label": "English",
  },
};

export function tl(lang: Lang, key: string, replacements?: Record<string, string | number>): string {
  let text = t[lang]?.[key] || t.en[key] || key;
  if (replacements) {
    for (const [k, v] of Object.entries(replacements)) {
      text = text.replace(`{${k}}`, String(v));
    }
  }
  return text;
}
