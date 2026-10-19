# -*- coding: utf-8 -*-
"""Module kích hoạt: Định danh, OTA, HTTP client và UI factory."""

from .factory import create_activation_ui
from .service import ActivationService

__all__ = ["ActivationService", "create_activation_ui"]
