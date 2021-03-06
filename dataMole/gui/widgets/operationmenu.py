# -*- coding: utf-8 -*-
#
# Author:       Alessandro Zangari (alessandro.zangari.code@outlook.com)
# Copyright:    © Copyright 2020 Alessandro Zangari, Università degli Studi di Padova
# License:      GPL-3.0-or-later
# Date:         2020-10-04
# Version:      1.0
#
# This file is part of DataMole.
#
# DataMole is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
#
# DataMole is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with DataMole.  If not, see <https://www.gnu.org/licenses/>.

import importlib
from typing import Callable, List

from PySide2.QtCore import Qt, QPoint, QMimeData, Slot
from PySide2.QtGui import QMouseEvent, QDrag, QStandardItem, QStandardItemModel
from PySide2.QtWidgets import QWidget, QTreeWidget, QTreeWidgetItem, QApplication

from dataMole.operation import __all_modules__  # contains all modules with operations
from dataMole.operation.interface.graph import GraphOperation


def _build_item(name: str, data: type = None) -> QTreeWidgetItem:
    """
    Build a tree item with a display name, and sets its data

    :param data: the class name. If specified it's set at column 1 on Qt.UserRole

    """

    item = QTreeWidgetItem([name])
    flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
    if data:
        item.setData(1, Qt.UserRole, data)
        # Show the short description as tooltip of the items
        if data.shortDescription():
            item.setData(0, Qt.ToolTipRole, data.shortDescription())
        flags |= Qt.ItemIsDragEnabled
    item.setFlags(flags)
    return item


def _addChildren(parents: List[QTreeWidgetItem], op_class: Callable) -> None:
    op_name = getattr(op_class, 'name')()
    if issubclass(op_class, GraphOperation):
        op_input: bool = getattr(op_class, 'maxInputNumber')() == 0
        op_output: bool = getattr(op_class, 'minOutputNumber')() == 0
        if op_input:
            parents[0].addChild(_build_item(op_name, data=op_class))
        elif op_output:
            parents[1].addChild(_build_item(op_name, data=op_class))
        else:
            parents[2].addChild(_build_item(op_name, data=op_class))
    else:
        # If it's an Operation then child is added normally but hidden, since only GraphOperations
        # should be shown
        item = _build_item(op_name, data=op_class)
        parents[2].addChild(item)
        item.setHidden(True)


class OperationMenu(QTreeWidget):
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.__dragStartPosition: QPoint = None
        self.setSelectionMode(QTreeWidget.SingleSelection)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.headerItem().setText(0, 'Operations')
        # Parent items (categories)
        top_items = list(map(_build_item, ['Input', 'Output', 'All']))
        self.addTopLevelItems(top_items)
        # Import everything in operations directory
        var_export = 'export'
        for moduleName in __all_modules__:
            module = importlib.import_module(moduleName)
            if not hasattr(module, var_export):
                continue
            op_class = getattr(module, var_export)
            if isinstance(op_class, list) or isinstance(op_class, tuple):
                for c in op_class:
                    _addChildren(top_items, c)
            else:
                _addChildren(top_items, op_class)

        self.__expanded: bool = False
        self.header().setDefaultAlignment(Qt.AlignCenter)
        self.header().setSectionsClickable(True)
        self.header().sectionClicked.connect(self.toggleExpansion)
        self.setUniformRowHeights(True)
        self.sortItems(0, Qt.SortOrder.AscendingOrder)

    def model(self) -> QStandardItemModel:
        items: List[QTreeWidgetItem] = \
            self.findItems('*', Qt.MatchWrap | Qt.MatchWildcard | Qt.MatchRecursive)
        model = QStandardItemModel()

        def standardItem(w: QTreeWidgetItem) -> QStandardItem:
            s = QStandardItem()
            s.setData(w.data(0, Qt.DisplayRole), Qt.DisplayRole)
            s.setData(w.data(1, Qt.UserRole), Qt.UserRole)
            s.setData(w.data(0, Qt.ToolTipRole), Qt.ToolTipRole)
            return s

        def filterItems(item: QTreeWidgetItem) -> bool:
            op_class: type = item.data(1, Qt.UserRole)
            keep: bool = bool(item.parent())
            if keep and issubclass(op_class, GraphOperation):
                keep &= op_class.minInputNumber() == op_class.maxInputNumber() == 1 \
                        and op_class.minOutputNumber() == 1
            else:
                keep &= item.isHidden()
            return keep

        items = list(map(standardItem, filter(filterItems, items)))
        for i in items:
            model.appendRow(i)
        return model

    @Slot(int)
    def toggleExpansion(self, section: int) -> None:
        if section == 0:
            self.__expanded = not self.__expanded
            if self.__expanded:
                self.expandAll()
            else:
                self.collapseAll()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.__dragStartPosition: QPoint = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if not event.buttons() and Qt.LeftButton:
            return
        # Test if item is drag enabled
        clicked_item = self.itemAt(self.__dragStartPosition)
        if clicked_item and not bool(clicked_item.flags() & Qt.ItemIsDragEnabled):
            return
        if (event.pos() - self.__dragStartPosition).manhattanLength() < QApplication.startDragDistance():
            return

        drag: QDrag = QDrag(self)
        mimeData: QMimeData = QMimeData()
        mimeData.setText('operation')

        drag.setMimeData(mimeData)
        drag.exec_()

    def getDropData(self) -> Callable:
        op = self.itemAt(self.__dragStartPosition).data(1, Qt.UserRole)
        self.__dragStartPosition = None
        return op
