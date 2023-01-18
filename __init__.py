# Copyright (c) 2023 5@xes
# Initialy Based on the SupportBlocker plugin by Ultimaker B.V., and licensed under LGPLv3 or higher.

VERSION_QT5 = False
try:
    from PyQt6.QtCore import QT_VERSION_STR
except ImportError:
    VERSION_QT5 = True
    
from . import CustomSupportEraserPlus

from UM.i18n import i18nCatalog
i18n_catalog = i18nCatalog("customsupporteraser")

def getMetaData():
    if not VERSION_QT5:
        QmlFile="qml_qt6/CustomSupportEraser.qml"
    else:
        QmlFile="qml_qt5/CustomSupportEraser.qml"

    return {
        "tool": {
            "name": i18n_catalog.i18nc("@label", "Custom Supports Eraser Plus"),
            "description": i18n_catalog.i18nc("@info:tooltip", "Add 3 types of custom support eraser"),
            "icon": "tool_icon.svg",
            "tool_panel": QmlFile,
            "weight": 7
        }
    }

def register(app):
    return { "tool": CustomSupportEraserPlus.CustomSupportEraserPlus() }
