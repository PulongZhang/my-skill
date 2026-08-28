#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""日报 Git、Claude Code 与 Codex 数据源共用的项目目录范围。"""

import re
from pathlib import PureWindowsPath
from typing import Iterable, List


# 三个提取器必须共同使用此配置，避免默认扫描范围产生偏差。
DEFAULT_PROJECT_ROOTS = [r"D:\CETWorkSpace"]


def normalize_project_roots(paths: Iterable[str]) -> List[str]:
    """统一 Windows 盘符路径格式，保留非 Windows 路径。"""
    normalized: List[str] = []
    for path in paths:
        if re.match(r"^[A-Za-z]:[\\/]", path):
            path = str(PureWindowsPath(path)).replace("\\", "/")
        normalized.append(path)
    return normalized
