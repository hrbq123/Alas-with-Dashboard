# 此文件专门用于统计分析大世界（Operation Siren）的月度练级效率与资源投入数据。
# 负责读写 cl1_monthly.json 本地统计文件，并具备通过正则解析日志历史记录以辅助计算行动力获取总额的功能。
from __future__ import annotations

from pathlib import Path
import json
from datetime import datetime
from typing import Dict, Any, Optional

from module.logger import logger


class OpsiMonthStats:
    def __init__(self, path: Path | None = None, instance_name: str | None = None) -> None:
        if path is None:
            project_root = Path(__file__).resolve().parents[2]
            if instance_name:
                self._path = project_root / "log" / "cl1" / instance_name / "cl1_monthly.json"
            else:
                self._path = project_root / "log" / "cl1" / "default" / "cl1_monthly.json"
        else:
            self._path = Path(path)
        self._instance_name = instance_name or "default"

    def _load_raw(self) -> Dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, dict):
                    return data
                else:
                    logger.warning("CL1 monthly file is not a dict, ignoring")
                    return {}
        except Exception:
            logger.exception("Failed to load CL1 monthly file")
            return {}

    def summary(self, year: int | None = None, month: int | None = None) -> Dict[str, Any]:
        now = datetime.now()
        if year is None:
            year = now.year
        if month is None:
            month = now.month
        key = f"{year:04d}-{month:02d}"

        data = self._load_raw()
        v = data.get(key, 0)
        try:
            total = int(v)
        except Exception:
            total = 0

        akashi_key = f"{key}-akashi"
        akashi_v = data.get(akashi_key, 0)
        try:
            akashi = int(akashi_v)
        except Exception:
            akashi = 0

        return {"month": key, "total_battles": total, "akashi_encounters": akashi, "raw": data}

    def get_detailed_summary(self, year: int | None = None, month: int | None = None) -> Dict[str, Any]:
        """
        获取详细的统计摘要,包含所有计算指标
        
        Args:
            year: 年份 (默认当前年份)
            month: 月份 (默认当前月份)
        
        Returns:
            包含详细统计数据的字典
        """
        now = datetime.now()
        if year is None:
            year = now.year
        if month is None:
            month = now.month
        key = f"{year:04d}-{month:02d}"

        data = self._load_raw()
        
        # 基础数据
        battle_count = int(data.get(key, 0))
        akashi_encounters = int(data.get(f"{key}-akashi", 0))
        akashi_ap = int(data.get(f"{key}-akashi-ap", 0))
        
        # 如果没有明确的akashi-ap字段,尝试从entries计算
        if akashi_ap == 0:
            entries = data.get(f"{key}-akashi-ap-entries", [])
            if isinstance(entries, list):
                for entry in entries:
                    try:
                        if isinstance(entry, dict):
                            akashi_ap += int(entry.get('amount', 0))
                        else:
                            akashi_ap += int(entry)
                    except Exception:
                        continue
        
        # 计算衍生指标
        battle_rounds = battle_count // 2
        sortie_cost = battle_rounds * 120
        
        akashi_probability = round(akashi_encounters / battle_count, 4) if battle_count > 0 else 0.0
        average_stamina = round(akashi_ap / akashi_encounters, 2) if akashi_encounters > 0 else 0.0
        
        return {
            "month": key,
            "battle_count": battle_count,
            "battle_rounds": battle_rounds,
            "sortie_cost": sortie_cost,
            "akashi_encounters": akashi_encounters,
            "akashi_probability": akashi_probability,
            "average_stamina": average_stamina,
            "net_stamina_gain": akashi_ap,
        }



_singleton: Dict[str, OpsiMonthStats] = {}


def get_opsi_stats(instance_name: str | None = None) -> OpsiMonthStats:
    global _singleton
    key = instance_name or "default"
    if key not in _singleton:
        _singleton[key] = OpsiMonthStats(instance_name=instance_name)
    return _singleton[key]


__all__ = ["get_opsi_stats", "OpsiMonthStats", "compute_monthly_cl1_akashi_ap"]



def compute_monthly_cl1_akashi_ap(year: int | None = None, month: int | None = None, campaign: str = "opsi_akashi", instance_name: str | None = None) -> int:
    from pathlib import Path
    import json
    import csv
    import re
    from datetime import datetime

    now = datetime.now()
    if year is None:
        year = now.year
    if month is None:
        month = now.month
    key_prefix = f"{year:04d}-{month:02d}"

    project_root = Path(__file__).resolve().parents[2]
    instance_dir = instance_name or "default"

    try:
        fpath = project_root / "log" / "cl1" / instance_dir / "cl1_monthly.json"
        if fpath.exists():
            try:
                data = json.loads(fpath.read_text(encoding="utf-8")) or {}
            except Exception:
                data = {}

            ap_key = f"{key_prefix}-akashi-ap"
            if ap_key in data:
                try:
                    return int(data.get(ap_key, 0))
                except Exception:
                    return 0

            entries_key = f"{key_prefix}-akashi-ap-entries"
            entries = data.get(entries_key)
            if isinstance(entries, list) and entries:
                total = 0
                for e in entries:
                    try:
                        total += int(e.get("amount", 0)) if isinstance(e, dict) else int(e)
                    except Exception:
                        continue
                return int(total)
    except Exception:
        pass

    total_ap_from_logs = 0
    try:
        log_dir = project_root / "log"
        if log_dir.exists() and log_dir.is_dir():
            for lf in sorted(log_dir.iterdir()):
                if not lf.is_file():
                    continue
                if lf.suffix.lower() not in (".log", ".txt"):
                    continue
                try:
                    mtime = datetime.fromtimestamp(lf.stat().st_mtime)
                except Exception:
                    mtime = None
                if mtime is not None and (mtime.year != year or mtime.month != month):
                    continue

                try:
                    text = lf.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    try:
                        text = lf.read_text(encoding="gbk", errors="ignore")
                    except Exception:
                        continue

                lines = text.splitlines()
                for idx, line in enumerate(lines):
                    if "ActionPoint" in line and "Click" in line:
                        window = "\n".join(lines[idx: idx + 25])
                        if "Shop buy finished" in window:
                            m = re.search(r"ActionPoint(\d+)(?:_(\d+)x)?", line)
                            if m:
                                try:
                                    base = int(m.group(1))
                                    mult = int(m.group(2)) if m.group(2) else 1
                                    total_ap_from_logs += base * mult
                                except Exception:
                                    continue

        if total_ap_from_logs > 0:
            return int(total_ap_from_logs)
    except Exception:
        pass

    total_ap = 0
    screenshots_dir = project_root / "screenshots" / campaign
    if screenshots_dir.exists() and screenshots_dir.is_dir():
        for f in screenshots_dir.iterdir():
            if not f.is_file() or f.suffix.lower() != ".csv":
                continue
            for enc in ("utf-8", "gbk", "latin-1"):
                try:
                    with f.open("r", encoding=enc, errors="ignore") as fh:
                        reader = csv.reader(fh)
                        for row in reader:
                            if not row or len(row) < 3:
                                continue
                            item_name = str(row[1])
                            item_amount = str(row[2])
                            name_l = item_name.lower()
                            if ("action" in name_l and "point" in name_l) or "actionpoint" in name_l:
                                m = re.search(r"(\d+)", item_amount)
                                if not m:
                                    m = re.search(r"(\d+)", item_name)
                                if m:
                                    try:
                                        total_ap += int(m.group(1))
                                    except Exception:
                                        continue
                    break
                except Exception:
                    continue

    return int(total_ap)


__all__.append("compute_monthly_cl1_akashi_ap")
