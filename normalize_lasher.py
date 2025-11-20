#!/usr/bin/env python3
import os
import re
import sys
import argparse
from pathlib import Path

DIGITS = re.compile(r'(\d+)')

def extract_num6(name: str):
    """只取文件名里的数字，拼成一个整数，再格式化为6位，不存在数字则返回None。"""
    """extract text digits from filename and format as 6-digit string """
    nums = DIGITS.findall(name)
    if not nums:
        return None
    # 把所有数字片段拼起来，例如 'v0_63' -> '063'
    # assemble all digit parts, e.g. 'v0_63' -> '063'
    s = ''.join(nums)
    try:
        n = int(s)
    except ValueError:
        return None
    return f"{n:06d}"

def normalize_real_files(root: Path, dry_run: bool):
    """第一步：把所有真实jpg文件重命名为6位数字名。"""
    """Rename all real jpg files to 6-digit numeric names."""
    changes = []
    conflicts = []
    for p in root.rglob("*.jpg"):
        try:
            if p.is_symlink():
                continue
            if not p.is_file():
                continue
            num6 = extract_num6(p.name)
            if num6 is None:
                print(f"[WARN][REAL] No digits in filename, skip: {p}")
                continue
            newp = p.with_name(num6 + p.suffix.lower())
            if p.name == newp.name:
                continue  # already normalized
            if newp.exists():
                # 如果已存在同名目标，避免覆盖，保留现有并记录冲突
                # If target exists, avoid overwrite, keep existing and record conflict
                conflicts.append((p, newp))
                print(f"[CONFLICT][REAL] {p} -> {newp} (target exists, skip rename)")
                continue
            changes.append((p, newp))
        except Exception as e:
            print(f"[ERROR][REAL] {p}: {e}")

    # 执行重命名
    # Perform renames
    for old, new in changes:
        print(f"[RENAME][REAL] {old} -> {new}")
        if not dry_run:
            old.rename(new)

    return changes, conflicts

def fix_symlinks(root: Path, dry_run: bool):
    """第二步：让每个 symlink（如 000063.jpg）按其自身名字的数字指向同目录 6位数字文件。"""
    """Step 2: Make each symlink (e.g., 000063.jpg) point to the 6-digit file in the same directory."""
    fixed = []
    broken = []
    retargeted = []
    for p in root.rglob("*.jpg"):
        try:
            if not p.is_symlink():
                continue
            # 以 symlink 名字为准提取数字（例如 000063.jpg -> 000063）
            # Extract digits from symlink name (e.g., 000063.jpg -> 000063)
            num6 = extract_num6(p.name)
            if num6 is None:
                print(f"[WARN][LINK] No digits in symlink name, skip: {p}")
                continue
            target_canonical = p.with_name(num6 + p.suffix.lower())  # 同目录下目标 Same directory target
            # 判断当前链接是否已经正确
            # Check if current link is already correct
            try:
                current_target = os.readlink(p)
            except OSError:
                current_target = None

            # 如果目标真实文件存在，就把 symlink 指向它
            # If the target real file exists, point the symlink to it
            if target_canonical.exists() and target_canonical.is_file() and not target_canonical.is_symlink():
                # 规范化为相对路径
                # Normalize to relative path
                rel = os.path.relpath(target_canonical, start=p.parent)
                if current_target != rel:
                    print(f"[RETARGET][LINK] {p} -> {rel}")
                    if not dry_run:
                        # ln -snf rel p
                        if p.exists() or p.is_symlink():
                            p.unlink()
                        os.symlink(rel, p)
                    retargeted.append((p, rel))
                else:
                    fixed.append(p)
            else:
                # 目标不存在，记录坏链接
                # Target does not exist, record broken link
                print(f"[BROKEN][LINK] {p} -> {current_target} (missing {target_canonical})")
                broken.append((p, current_target, target_canonical))
        except Exception as e:
            print(f"[ERROR][LINK] {p}: {e}")

    return fixed, retargeted, broken

def main():
    ap = argparse.ArgumentParser(description="Normalize LasHeR jpg names to 6-digit and fix symlinks.")
    ap.add_argument("root", type=str, help="dataset root (e.g., /scratch/.../LasHeR/train/trainingset)")
    ap.add_argument("--apply", action="store_true", help="apply changes (otherwise dry-run)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"Root not found: {root}")
        sys.exit(1)

    dry = not args.apply
    print(f"== Step 1: normalize real files under {root} (dry_run={dry}) ==")
    real_changes, real_conflicts = normalize_real_files(root, dry)

    print(f"\n== Step 2: fix symlinks to point to 6-digit files (dry_run={dry}) ==")
    fixed, retargeted, broken = fix_symlinks(root, dry)

    print("\n== SUMMARY ==")
    print(f"Real file renames: {len(real_changes)}")
    print(f"Real file conflicts (skipped): {len(real_conflicts)}")
    print(f"Symlinks already correct: {len(fixed)}")
    print(f"Symlinks retargeted: {len(retargeted)}")
    print(f"Broken symlinks (missing targets): {len(broken)}")
    if broken:
        print("\nBroken examples:")
        for i, (link, cur, want) in enumerate(broken[:20], 1):
            print(f"  {i}. {link} -> {cur}, expected {want}")

if __name__ == "__main__":
    main()