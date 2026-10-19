"""Định danh thiết bị và lưu trữ efuse (Device Identity & efuse).

efuse.json chỉ lưu trữ các trường phẳng (không ghi lồng device_fingerprint)::

    {
      "mac_address": "...",
      "serial_number": "...",
      "hmac_key": "...",
      "activation_status": false
    }

Khi sinh SN/HMAC vẫn thu thập fingerprint trong bộ nhớ, không ghi xuống đĩa.
Nếu file cũ có device_fingerprint, khi tải/xác thực sẽ bóc tách và ghi đè lại.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
from pathlib import Path
from typing import Dict, Optional, Tuple

import machineid
import psutil

from src.logging import get_logger
from src.utils.resource_finder import get_user_data_dir

logger = get_logger()

# Các trường lưu trữ lâu dài (phẳng); các khóa khác (như device_fingerprint lịch sử) sẽ bị loại bỏ khi tải
_EFUSE_KEYS = (
    "mac_address",
    "serial_number",
    "hmac_key",
    "activation_status",
)


class DeviceIdentity:
    """Đọc/ghi file efuse, số serial / HMAC / MAC."""

    def __init__(self) -> None:
        self._system = platform.system()
        self._efuse_file: Optional[Path] = None
        self._efuse_cache: Optional[Dict] = None

    def init_paths(self) -> None:
        config_dir = get_user_data_dir() / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        self._efuse_file = config_dir / "efuse.json"
        logger.debug(f"Đường dẫn file efuse: {self._efuse_file}")

    def ensure_efuse_file(self) -> None:
        fingerprint = self.generate_fresh_fingerprint()
        mac_address = fingerprint.get("mac_address")
        if not self._efuse_file or not self._efuse_file.exists():
            logger.info("Tạo file efuse.json")
            self._create_efuse_file(fingerprint, mac_address)
        else:
            self._validate_efuse_file(fingerprint, mac_address)

    def ensure_device_identity(self) -> Tuple[Optional[str], Optional[str], bool]:
        data = self.load_efuse_data()
        return (
            data.get("serial_number"),
            data.get("hmac_key"),
            data.get("activation_status", False),
        )

    def get_serial_number(self) -> Optional[str]:
        return self.load_efuse_data().get("serial_number")

    def get_mac_address(self) -> Optional[str]:
        return self.load_efuse_data().get("mac_address")

    def is_activated(self) -> bool:
        return bool(self.load_efuse_data().get("activation_status", False))

    def set_activation_status(self, status: bool) -> bool:
        data = self.load_efuse_data()
        data["activation_status"] = bool(status)
        return self._save_efuse_data(data)

    def generate_hmac_signature(self, challenge: str) -> Optional[str]:
        hmac_key = self.load_efuse_data().get("hmac_key")
        if not hmac_key or not challenge:
            return None
        return hmac.new(
            hmac_key.encode(), challenge.encode(), hashlib.sha256
        ).hexdigest()

    def load_efuse_data(self) -> Dict:
        if self._efuse_cache is not None:
            return self._efuse_cache
        try:
            return self._load_efuse_data_from_file()
        except Exception:
            return {"activation_status": False}

    def generate_fresh_fingerprint(self) -> Dict:
        """Thu thập trong bộ nhớ, chỉ dùng để tạo SN/HMAC; không ghi vào efuse.json."""
        return {
            "system": self._system,
            "hostname": platform.node(),
            "mac_address": self._get_primary_mac_address(),
            "machine_id": self._get_machine_id(),
        }

    def _flat_efuse(
        self,
        *,
        mac_address: Optional[str],
        serial_number: str,
        hmac_key: str,
        activation_status: bool = False,
    ) -> Dict:
        return {
            "mac_address": mac_address,
            "serial_number": serial_number,
            "hmac_key": hmac_key,
            "activation_status": bool(activation_status),
        }

    def _create_efuse_file(self, fingerprint: Dict, mac_address: Optional[str]):
        serial_number = self._generate_serial_number_from_fingerprint(fingerprint)
        hmac_key = self._generate_hmac_key_from_fingerprint(fingerprint)
        efuse_data = self._flat_efuse(
            mac_address=mac_address,
            serial_number=serial_number,
            hmac_key=hmac_key,
            activation_status=False,
        )
        self._save_efuse_data(efuse_data)
        logger.info(f"Đã tạo cấu hình efuse: Số serial={serial_number}")

    def _validate_efuse_file(self, fingerprint: Dict, mac_address: Optional[str]):
        try:
            with open(self._efuse_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                raise TypeError(
                    f"Node gốc của efuse phải là object, thực tế là {type(raw).__name__}"
                )

            had_extra = any(k not in _EFUSE_KEYS for k in raw)
            missing = [f for f in _EFUSE_KEYS if f not in raw]
            if missing:
                logger.warning(f"efuse thiếu các trường: {missing}")
                for field in missing:
                    if field == "mac_address":
                        raw[field] = mac_address
                    elif field == "serial_number":
                        raw[field] = self._generate_serial_number_from_fingerprint(
                            fingerprint
                        )
                    elif field == "hmac_key":
                        raw[field] = self._generate_hmac_key_from_fingerprint(
                            fingerprint
                        )
                    elif field == "activation_status":
                        raw[field] = False

            flat = self._normalize_efuse_dict(raw)
            if missing or had_extra:
                if had_extra:
                    logger.info(
                        "efuse đã loại bỏ các trường không phẳng (như device_fingerprint)"
                    )
                self._save_efuse_data(flat)
            else:
                self._efuse_cache = flat
        except Exception as e:
            logger.error(f"Xác thực efuse thất bại: {e}, tạo lại", exc_info=True)
            self._create_efuse_file(fingerprint, mac_address)

    def _normalize_efuse_dict(self, data: Dict) -> Dict:
        """Chỉ giữ lại các trường định danh phẳng."""
        return {
            "mac_address": data.get("mac_address"),
            "serial_number": data.get("serial_number"),
            "hmac_key": data.get("hmac_key"),
            "activation_status": bool(data.get("activation_status", False)),
        }

    def _get_primary_mac_address(self) -> Optional[str]:
        try:
            for iface, addrs in psutil.net_if_addrs().items():
                if iface.lower().startswith(("lo", "loopback")):
                    continue
                for snic in addrs:
                    if snic.family == psutil.AF_LINK and snic.address:
                        mac = self._normalize_mac(snic.address)
                        if mac != "00:00:00:00:00:00":
                            return mac
        except Exception as e:
            logger.error(f"Lấy địa chỉ MAC thất bại: {e}", exc_info=True)
        return None

    def _normalize_mac(self, mac: str) -> str:
        clean = "".join(c for c in mac if c.isalnum())
        if len(clean) != 12:
            return mac.lower()
        return ":".join(clean[i : i + 2] for i in range(0, 12, 2)).lower()

    def _get_machine_id(self) -> Optional[str]:
        try:
            return machineid.id()
        except Exception as e:
            logger.warning(f"Lấy machine_id thất bại: {e}", exc_info=True)
            return None

    def _generate_serial_number_from_fingerprint(self, fingerprint: Dict) -> str:
        mac = fingerprint.get("mac_address")
        if mac:
            mac_clean = mac.lower().replace(":", "")
            short_hash = hashlib.md5(mac_clean.encode()).hexdigest()[:8].upper()
            return f"SN-{short_hash}-{mac_clean}"
        machine_id = fingerprint.get("machine_id")
        hostname = fingerprint.get("hostname")
        identifier = (machine_id or hostname or "unknown")[:12]
        short_hash = hashlib.md5(identifier.encode()).hexdigest()[:8].upper()
        return f"SN-{short_hash}-{identifier.upper()}"

    def _generate_hmac_key_from_fingerprint(self, fingerprint: Dict) -> str:
        identifiers = []
        for key in ["hostname", "mac_address", "machine_id"]:
            if fingerprint.get(key):
                identifiers.append(fingerprint[key])
        if not identifiers:
            identifiers.append(self._system)
        return hashlib.sha256("||".join(identifiers).encode()).hexdigest()

    def _load_efuse_data_from_file(self) -> Dict:
        with open(self._efuse_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise TypeError(f"Node gốc của efuse phải là object, thực tế là {type(data).__name__}")
        # Dữ liệu trong bộ nhớ luôn phẳng; các khóa thừa trên đĩa do ensure/validate bóc tách và ghi lại
        flat = self._normalize_efuse_dict(data)
        self._efuse_cache = flat
        return flat

    def _save_efuse_data(self, data: Dict) -> bool:
        try:
            if not self._efuse_file:
                raise RuntimeError("Đường dẫn efuse chưa được khởi tạo")
            flat = self._normalize_efuse_dict(data)
            self._efuse_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._efuse_file.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(flat, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            os.replace(tmp, self._efuse_file)
            self._efuse_cache = flat
            return True
        except Exception as e:
            logger.error(f"Lưu efuse thất bại: {e}", exc_info=True)
            return False
