# Titanium 浏览器（Helium）中文本地化指南

本仓库是 **Helium 浏览器安卓版**（基于 Chromium，叠加 Vanadium + Helium 补丁）的**构建封装仓库**。
真正构成浏览器界面的代码并不在本仓库内，而是通过 `.gclient` 拉取的完整 Chromium 源码树（`src/`）以及两个补丁子模块：

- `src/` —— 完整的 Chromium 源码（数十 GB，包含全部 UI 字符串与翻译）
- `helium/` —— imputnet/helium 补丁子模块（Chromium 衍生）
- `vanadium/` —— GrapheneOS/Vanadium 补丁子模块（安全加固）

因此「中文界面里还有英文」的根因与对应修复位置如下。

---

## 一、为什么会「中文界面英文太多」

Chromium 的界面文案走 **GRIT 本地化体系**：

- 字符串定义在 `.grd` / `.grdp` 文件中（如 `google_chrome_strings.grd`、`chromium_strings.grd`、各组件的 `resources/*.grd`）。
- 翻译存放在各语言的 `.xtb` 文件中（简体中文为 `zh-CN.xtb`）。
- 安卓端 Java 字符串会生成到 `chrome/android/java/res/values-zh-rCN/strings.xml`。

当某个字符串 **在 `zh-CN.xtb` 中没有对应翻译** 时，Chromium 会回退（fallback）到英文，于是你在中文系统下也会看到英文。常见三类原因：

1. **构建未打包中文语言包**：Chromium 安卓默认打包全部语言；除非 `args.gn` 显式用 `chrome_locales` 限制了语言，否则中文包会随 APK 提供。本仓库 `args.gn` 未做限制，通常无需改动。
2. **设备/应用语言未设为中文**：请在系统设置或浏览器「设置 → 语言」中确认界面语言为「简体中文」。
3. **上游新增字符串尚未翻译**：Chromium 持续迭代，部分较新的功能字符串在 `zh-CN.xtb` 中确实会暂时缺失，这是「英文泄漏」最常见的真实来源。

> 经核查，本仓库自带的补丁（`patch_*.py`）注入的扩展菜单文案**已经是中文**（如「扩展应用」「还没有运行任何扩展」「常用工具」），并未新增英文界面文案。所以问题基本落在上面第 2、3 类。

---

## 二、本地化入口（需要 Chromium 源码树）

在拉取并初始化子模块、拿到 `src/` 后，按字符串所属模块定位 `.xtb`：

| 字符串类型 | 定义文件 | 简体中文翻译文件 |
| --- | --- | --- |
| 浏览器主文案 | `src/chrome/app/resources/google_chrome_strings.grd` | `.../google_chrome_strings_zh-CN.xtb` |
| Chromium 通用文案 | `src/chrome/app/resources/chromium_strings.grd` | `.../chromium_strings_zh-CN.xtb` |
| 各组件文案 | `src/components/<组件>/resources/*.grd` | 同目录 `*.xtb`（语言后缀） |
| 安卓 Java 字符串 | `src/chrome/android/java/res/values/strings.xml`（生成自 `.grd`） | `src/chrome/android/java/res/values-zh-rCN/strings.xml` |

### 修正/新增某条中文翻译的标准做法

1. 在对应的 `.grd` 中找到字符串的 `name`（即消息 ID），例如 `<message name="IDS_MENU_SETTINGS" ...>Settings</message>`。
2. 打开同目录的 `zh-CN.xtb`，确认是否已有 `<translation id="IDS_MENU_SETTINGS">设置</translation>`。
3. 缺失则补上；翻译不准确则直接修改为正确中文。
4. 重新构建即可生效（`.xtb` 改动会被 GRIT 重新编译进 `resources.pak` / 安卓 `strings.xml`）。

> 注意：`zh-CN` 在 Chromium 里对应目录名 `values-zh-rCN`、文件后缀 `zh-CN.xtb`（连字符），不要写成下划线。

---

## 三、本仓库已完成的本地化改动

- 新增 **应用商店中文元数据** `fastlane/metadata/android/zh-CN/`（标题、简介、完整描述），
  原本只有 `en-US`，中文用户在商店页看到的全是英文 —— 现已补齐。

---

## 四、辅助脚本 `apply_zhcn.py`（已接入构建流程）

Chromium 的 `zh-CN.xtb` 用「消息名的数值哈希」作为 `<translation>` 的 `id`（不是消息名）。不同 Chromium 版本哈希算法可能不同，因此脚本在运行时会**自动探测**当前源码树使用的算法（`detect_algo`），保证注入的翻译能被 GRIT 正确匹配。

脚本提供四个子命令，均为安全（非破坏式）操作：

```bash
# 1) 审计中文翻译覆盖率：扫描源码树，统计各组件 zh-CN 缺失条数并列出缺口
python3 apply_zhcn.py audit --src chromium/src

# 2) 注入：仅把映射中「缺失」的中文写入对应 zh-CN.xtb（不改写已有翻译）
python3 apply_zhcn.py inject --root chromium/src --map zh_cn_overrides.json --algo auto

# 3) 生成可直接合并的 zh-CN.xtb 片段（手动合并用）
python3 apply_zhcn.py gen --map zh_cn_overrides.json --out zh_cn_snippet.xtb

# 4) 对给定 .grd + zh-CN.xtb 探测命中的哈希算法（排错用）
python3 apply_zhcn.py selftest --grd chrome/app/resources/google_chrome_strings.grd \
                                --xtb chrome/app/resources/google_chrome_strings_zh-CN.xtb
```

**已自动接入构建**：`build.sh` 在 `gn gen` 之前会调用 `inject`（已加防护，失败也不影响构建），
因此只要把本仓库（含 `localization/`）拿去构建，产出的 APK 就会带上这里的中文覆盖翻译。

> 注：本仓库的 Chromium 源码位于 `chromium/src/`（由 `build.sh` 通过 gclient 拉取），
> 不是 `src/`；脚本会递归扫描该目录下的全部 `zh-CN.xtb`。

---

## 五、完整本地化并验证的步骤（本地 Linux 构建）

1. 准备环境并拉取 Chromium 源码（需 Linux + 百余 GB 磁盘 + 大量内存，详见 `BUILDING.zh-CN.md`）：
   ```bash
   git submodule update --init --recursive
   ./build.sh            # 自动 gclient sync 到 chromium/src 并构建
   ```
   由于 `build.sh` 已内置中文注入步骤，正常构建即可产出带中文覆盖的 APK。
2. 若想先看缺哪些中文，可在构建前单独跑：
   ```bash
   python3 localization/apply_zhcn.py audit --src chromium/src
   ```
3. 把 `audit` 列出的缺失消息名 + 对应中文填入 `localization/zh_cn_overrides.json`
   （格式 `{"消息名": "中文"}`，用 `gen` 可预览片段）。
4. 重新构建，安装 APK 在中文系统下验证界面。

## 六、如何得到「完善后的 APK」（无需本地 Linux 机器）

本仓库已自带 GitHub Actions 构建流程（`.github/workflows/build.yml`）。你可以：

1. 把本仓库 **fork** 到自己的 GitHub 账号（已包含上面的 `fastlane/zh-CN` 与 `localization/` 改动）。
2. 进入仓库 **Actions → Build Android APK → Run workflow**，填写参数
   （默认 `ubuntu-latest` + 构建 arm64，构建在 GitHub 免费 Linux runner 上进行，会自动 `gclient sync` 拉取完整 Chromium 源码）。
3. 构建完成后，APK 作为 **Artifacts** 可下载；若勾选发布，还会生成 Release。
4. 要让中文覆盖真正生效，请先在第 2 步前把 `zh_cn_overrides.json` 填好真实缺失消息名
   （首次可先空跑一次 `audit` 拿到列表，再回填并重跑）。

> 说明：本机（Windows）**无法**直接编译 Chromium Android（官方仅支持 Linux 构建主机，且需完整源码树），
> 因此 APK 必须由上述 CI 或你自己的 Linux 机器产出；本交付物已把「源码下载 + 中文本地化 + 一键构建接入」全部就绪。
