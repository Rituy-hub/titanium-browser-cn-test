#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Titanium / Helium 浏览器 中文本地化辅助脚本（非破坏式）

Chromium 的翻译文件 zh-CN.xtb 使用「消息名的数值哈希」作为 <translation> 的 id，
而不是消息名本身。不同 Chromium 版本采用的哈希算法可能不同，因此本脚本在运行
时自动探测当前源码树使用的算法（见 detect_algo），保证注入的翻译能被 GRIT 正确匹配。

功能：
  audit    扫描 Chromium 源码树，统计各组件 zh-CN 翻译覆盖率，并列出缺失条目
  inject   将 {"消息名": "中文"} 映射中「缺失」的翻译写入对应 zh-CN.xtb（仅新增，不改写已有）
  gen      根据映射生成可直接合并的 zh-CN.xtb 片段（数值 id）
  selftest 对给定 .grd + zh-CN.xtb 探测并报告命中的哈希算法

注意：本脚本不会删除/改写任何已有翻译，inject 仅在 id 缺失时追加，避免误改大型翻译文件。
"""

import argparse
import json
import re
import sys
from pathlib import Path

MASK64 = 0xFFFFFFFFFFFFFFFF
MASK32 = 0xFFFFFFFF

# 候选哈希算法：Chromium 不同版本/平台使用不同的消息 id 生成方式
ALGOS = {
    "fnv64": lambda s: _fold(lambda h, c: ((h * 0x100000001B3) & MASK64) ^ ord(c), s, MASK64),
    "mul32": lambda s: _fold(lambda h, c: ((h * 0x1003F) & MASK32) ^ (ord(c) * 0x1003F), s, MASK32),
    "mul64": lambda s: _fold(lambda h, c: ((h * 0x1000003) & MASK64) ^ (ord(c) * 0x1000003), s, MASK64),
}


def _fold(fn, s, mask):
    h = 0
    for c in s:
        h = fn(h, c) & mask
    return h


def hash_id(name: str, algo: str = "fnv64") -> int:
    return ALGOS[algo](name)


def find_files(root: str, suffix: str):
    p = Path(root)
    if not p.exists():
        return []
    return [x for x in p.rglob(f"*{suffix}")]


def read_ids(xtb: Path):
    if not xtb.exists():
        return set()
    try:
        txt = xtb.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return set()
    return {int(m) for m in re.findall(r'<translation[^>]*?\bid="(\d+)"', txt)}


def read_names(grd: Path):
    if not grd.exists():
        return []
    try:
        txt = grd.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    return re.findall(r'<message[^>]*?\bname="([^"]+)"', txt)


def detect_algo(grd: Path, xtb: Path):
    ids = read_ids(xtb)
    names = read_names(grd)
    if not ids or not names:
        return "fnv64"
    best, best_ratio = "fnv64", -1.0
    for name, fn in ALGOS.items():
        hit = sum(1 for n in names if fn(n) in ids)
        ratio = hit / len(names)
        if ratio > best_ratio:
            best, best_ratio = name, ratio
        if ratio >= 0.99:
            return name
    return best


def audit(src: str):
    src_path = Path(src)
    if not src_path.exists():
        print(f"[错误] 未找到 Chromium 源码目录: {src}", file=sys.stderr)
        return 1
    grds = find_files(src, ".grd") + find_files(src, ".grdp")
    total_en = total_zh = 0
    gaps = []
    for grd in grds:
        names = read_names(grd)
        if not names:
            continue
        xtb = grd.with_name(re.sub(r"\.(grd|grdp)$", "_zh-CN.xtb", grd.name))
        if not xtb.exists():
            continue
        algo = detect_algo(grd, xtb)
        ids = read_ids(xtb)
        present = sum(1 for n in names if hash_id(n, algo) in ids)
        en_n, zh_n = len(names), present
        total_en += en_n
        total_zh += zh_n
        gap = en_n - zh_n
        if gap > 0:
            gaps.append((str(grd.relative_to(src_path)), gap, algo))
        print(f"  {str(grd.relative_to(src_path)):<60} en={en_n:<5} zh-CN={zh_n:<5} 缺{gap} [{algo}]")
    print("\n== 汇总 ==")
    if total_en:
        print(f"  消息合计: {total_en}  中文已有: {total_zh}  覆盖率: {100.0*total_zh/total_en:.1f}%")
    else:
        print("  未发现可分析的 .grd / zh-CN.xtb 配对。")
    if gaps:
        print("  缺口最大的组件(建议优先补全):")
        for rel, gap, algo in sorted(gaps, key=lambda x: -x[1])[:15]:
            print(f"    - {rel} 缺 {gap} 条 [{algo}]")
    print("\n提示: 用本脚本 gen 生成片段、把缺失消息的中文填入 zh_cn_overrides.json 后 inject。")
    return 0


def inject(root: str, map_path: str, algo: str = "auto"):
    root_path = Path(root)
    mp = Path(map_path)
    if not mp.exists():
        print(f"[错误] 未找到映射文件: {map_path}", file=sys.stderr)
        return 1
    data = json.loads(mp.read_text(encoding="utf-8"))
    overrides = {k: v for k, v in data.items()
                 if not k.startswith("_") and isinstance(v, str) and v.strip()}
    if not overrides:
        print("[提示] 映射为空，无需注入。")
        return 0

    used_algo = algo
    if algo == "auto":
        for grd in find_files(root, ".grd"):
            xtb = grd.with_name(re.sub(r"\.(grd|grdp)$", "_zh-CN.xtb", grd.name))
            if xtb.exists():
                used_algo = detect_algo(grd, xtb)
                break
        if used_algo == "auto":
            used_algo = "fnv64"
    print(f"使用哈希算法: {used_algo}")

    xtbs = find_files(root, "zh-CN.xtb")
    if not xtbs:
        print(f"[错误] 在 {root} 下未找到 zh-CN.xtb", file=sys.stderr)
        return 1

    added_total = 0
    for xtb in xtbs:
        ids = read_ids(xtb)
        txt = xtb.read_text(encoding="utf-8", errors="ignore")
        new_nodes = []
        for name, zh in overrides.items():
            tid = hash_id(name, used_algo)
            if tid in ids:
                continue
            new_nodes.append(f'  <translation id="{tid}">{zh}</translation>')
            ids.add(tid)
        if new_nodes:
            if "</translationbundle>" in txt:
                txt = txt.replace("</translationbundle>",
                                  "\n".join(new_nodes) + "\n</translationbundle>")
            else:
                txt = txt.rstrip() + "\n" + "\n".join(new_nodes) + "\n</translationbundle>\n"
            xtb.write_text(txt, encoding="utf-8")
            added_total += len(new_nodes)
            print(f"  + {xtb}: 新增 {len(new_nodes)} 条")
    print(f"完成，共新增 {added_total} 条中文翻译（仅缺失项，不覆盖已有）。")
    return 0


def gen(map_path: str, out_path: str, algo: str = "fnv64"):
    mp = Path(map_path)
    if not mp.exists():
        print(f"[错误] 未找到映射文件: {map_path}", file=sys.stderr)
        return 1
    data = json.loads(mp.read_text(encoding="utf-8"))
    overrides = {k: v for k, v in data.items()
                 if not k.startswith("_") and isinstance(v, str) and v.strip()}
    out = Path(out_path)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<!DOCTYPE translationbundle SYSTEM "translationbundle.dtd">',
             '<translationbundle lang="zh-CN">']
    for name, zh in overrides.items():
        tid = hash_id(name, algo)
        lines.append(f'  <translation id="{tid}">{zh}</translation>')
    lines.append("</translationbundle>")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已生成 {len(overrides)} 条（算法 {algo}）-> {out}")
    print("请将 <translation> 节点按消息 id 合并进对应的 zh-CN.xtb。")
    return 0


def selftest(grd: str, xtb: str):
    g, x = Path(grd), Path(xtb)
    if not g.exists() or not x.exists():
        print("[错误] 需提供 .grd 与 zh-CN.xtb 路径", file=sys.stderr)
        return 1
    ids = read_ids(x)
    names = read_names(g)
    print(f"grd 消息数: {len(names)}  xtb 翻译数: {len(ids)}")
    for name, fn in ALGOS.items():
        hit = sum(1 for n in names if fn(n) in ids)
        ratio = (100.0 * hit / len(names)) if names else 0
        print(f"  算法 {name}: 命中 {hit}/{len(names)} ({ratio:.1f}%)")
    print(f"-> 推荐使用: {detect_algo(g, x)}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Titanium/Helium 中文本地化辅助工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a_audit = sub.add_parser("audit", help="审计 zh-CN 翻译覆盖率")
    a_audit.add_argument("--src", required=True, help="Chromium 源码树根目录")

    a_inject = sub.add_parser("inject", help="注入缺失中文翻译到 zh-CN.xtb")
    a_inject.add_argument("--root", required=True, help="Chromium 源码树根目录")
    a_inject.add_argument("--map", required=True, help="{\"消息名\": \"中文\"} JSON")
    a_inject.add_argument("--algo", default="auto", help="fnv64|mul32|mul64|auto(默认)")

    a_gen = sub.add_parser("gen", help="生成 zh-CN.xtb 片段")
    a_gen.add_argument("--map", required=True)
    a_gen.add_argument("--out", required=True)
    a_gen.add_argument("--algo", default="fnv64")

    a_st = sub.add_parser("selftest", help="探测 .grd/.xtb 使用的哈希算法")
    a_st.add_argument("--grd", required=True)
    a_st.add_argument("--xtb", required=True)

    args = ap.parse_args()
    if args.cmd == "audit":
        sys.exit(audit(args.src))
    if args.cmd == "inject":
        sys.exit(inject(args.root, args.map, args.algo))
    if args.cmd == "gen":
        sys.exit(gen(args.map, args.out, args.algo))
    if args.cmd == "selftest":
        sys.exit(selftest(args.grd, args.xtb))


if __name__ == "__main__":
    main()
