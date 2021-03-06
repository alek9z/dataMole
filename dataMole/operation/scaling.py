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

from typing import Iterable, Tuple, List, Dict, Optional

import pandas as pd
import prettytable as pt
from PySide2.QtCore import QModelIndex, Qt, QAbstractItemModel
from PySide2.QtWidgets import QStyledItemDelegate, QLineEdit, QHeaderView, QWidget
from sklearn.preprocessing import minmax_scale, scale

from dataMole import data, flogging, exceptions as exp
from dataMole.data.types import Type, Types
from dataMole.gui.editor import AbsOperationEditor, OptionsEditorFactory
from dataMole.gui.mainmodels import FrameModel
from dataMole.operation.interface.graph import GraphOperation
from dataMole.operation.utils import isFloat, splitString, NumericListValidator


class MinMaxScaler(GraphOperation, flogging.Loggable):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # { attr_index: (min, max) }
        self.__attributes: Dict[int, Tuple[float, float]] = dict()

    def logOptions(self) -> str:
        dfColumns = self.shapes[0].colNames
        # Logs options set in this operation
        tt = pt.PrettyTable(field_names=['Column', 'Range'])
        for k, v in self.__attributes.items():
            tt.add_row([dfColumns[k], '[{:G}, {:G}]'.format(*v)])
        return tt.get_string(border=True, vrules=pt.ALL)

    def execute(self, df: data.Frame) -> data.Frame:
        columns = df.getRawFrame().columns.to_list()
        # Execute
        pdf = df.getRawFrame().copy(True)
        fr = set(self.__attributes.values())
        if len(fr) == 1:
            # All ranges are the same, shortcut
            toProcess = pdf.iloc[:, list(self.__attributes.keys())]
            processedColNames = toProcess.columns
            scaled = minmax_scale(toProcess, feature_range=fr.pop(), axis=0, copy=True)
            processed = pd.DataFrame(scaled).set_index(pdf.index)
            processed.columns = processedColNames
        else:
            processed = dict()
            for k, fr in self.__attributes.items():
                processed[columns[k]] = minmax_scale(pdf.iloc[:, k], feature_range=fr, axis=0, copy=True)
            processed = pd.DataFrame(processed).set_index(pdf.index)
        # Merge result with other columns preserving order
        pdf = pdf.drop(columns=processed.columns)
        result = pd.concat([pdf, processed], ignore_index=False, axis=1)[columns]
        return data.Frame(result)

    @staticmethod
    def name() -> str:
        return 'MinMaxScaler'

    @staticmethod
    def shortDescription() -> str:
        return 'Scales columns as <code>[(X - X_min) / (X_max - X_min)] * (max - min) + min</code>'

    def acceptedTypes(self) -> List[Type]:
        return [Types.Numeric]

    def hasOptions(self) -> bool:
        return bool(self.__attributes)

    def unsetOptions(self) -> None:
        self.__attributes = dict()

    def needsOptions(self) -> bool:
        return True

    def getOptions(self) -> Iterable:
        return {'attributes': {k: {'range': v} for k, v in self.__attributes.items()}}

    def setOptions(self, attributes: Dict[int, Dict[str, Tuple[float, float]]]) -> None:
        # { attr_index: (min, max) }
        selectedAttributes: Dict[int, Tuple[float, float]] = dict()
        errors = list()
        if not attributes:
            raise exp.OptionValidationError([('noOptions', 'Error: no attributes are selected')])
        if not all(map(lambda v: bool(v), attributes.values())):
            errors.append(('notAllOptions', 'Error: some attributes have no options'))
        for k, opts in attributes.items():
            vRange = opts.get('range', None)
            if not vRange:
                raise exp.OptionValidationError([('nr', 'Error: no range is set at row {:d}'.format(k))])
            if not (len(vRange) == 2 and vRange[0] < vRange[1]):
                raise exp.OptionValidationError(
                    [('ir', 'Error: range is invalid at row {:d}'.format(k))])
            selectedAttributes[k] = vRange
        # Set options
        self.__attributes = selectedAttributes

    def getOutputShape(self) -> Optional[data.Shape]:
        if not self.hasOptions() or not self.shapes[0]:
            return None
        return self.shapes[0]

    def getEditor(self) -> AbsOperationEditor:
        factory = OptionsEditorFactory()
        factory.initEditor()
        factory.withAttributeTable(key='attributes',
                                   checkbox=True,
                                   nameEditable=False,
                                   showTypes=True,
                                   types=self.acceptedTypes(),
                                   options={
                                       'range': ('Range', _RangeDelegate(), None)
                                   })
        return factory.getEditor()

    def injectEditor(self, editor: AbsOperationEditor) -> None:
        editor.setSizeHint(500, 600)
        # Set frame model
        editor.attributes.setSourceFrameModel(FrameModel(editor, self.shapes[0]))
        # Stretch new section
        editor.attributes.tableView.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

    @staticmethod
    def minInputNumber() -> int:
        return 1

    @staticmethod
    def maxInputNumber() -> int:
        return 1

    @staticmethod
    def minOutputNumber() -> int:
        return 1

    @staticmethod
    def maxOutputNumber() -> int:
        return -1


class StandardScaler(GraphOperation, flogging.Loggable):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # List of attr_indexes
        self.__attributes: List[int] = list()

    def logOptions(self) -> None:
        dfColumns = self.shapes[0].colNames
        # Logs options set in this operation
        tt = pt.PrettyTable(field_names=['Column'])
        for attr in self.__attributes:
            tt.add_row([dfColumns[attr]])
        return tt.get_string(border=True, vrules=pt.ALL)

    def execute(self, df: data.Frame) -> data.Frame:
        columns = df.getRawFrame().columns.to_list()
        # Execute
        pdf = df.getRawFrame().copy(True)
        processedColNames = pdf.iloc[:, self.__attributes].columns
        scaled = scale(pdf.iloc[:, self.__attributes], with_mean=True, with_std=True, copy=True)
        processed = pd.DataFrame(scaled).set_index(pdf.index)
        processed.columns = processedColNames
        # Merge result with other columns preserving order
        pdf = pdf.drop(columns=processedColNames)
        result = pd.concat([pdf, processed], ignore_index=False, axis=1)[columns]
        return data.Frame(result)

    @staticmethod
    def name() -> str:
        return 'StandardScaler'

    @staticmethod
    def shortDescription() -> str:
        return '<p>Scales columns as (X - &mu;) / &sigma;</p>'

    def acceptedTypes(self) -> List[Type]:
        return [Types.Numeric]

    def hasOptions(self) -> bool:
        return bool(self.__attributes)

    def unsetOptions(self) -> None:
        self.__attributes = dict()

    def needsOptions(self) -> bool:
        return True

    def getOptions(self) -> Iterable:
        return {'attributes': {k: None for k in self.__attributes}}

    def setOptions(self, attributes: Dict[int, Dict]) -> None:
        # { attr_index: dict() }
        if not attributes:
            raise exp.OptionValidationError([('noOptions', 'Error: no attributes are selected')])
        # Set options
        self.__attributes = list(attributes.keys())

    def getOutputShape(self) -> Optional[data.Shape]:
        if not self.hasOptions() or not self.shapes[0]:
            return None
        return self.shapes[0]

    def getEditor(self) -> AbsOperationEditor:
        factory = OptionsEditorFactory()
        factory.initEditor()
        factory.withAttributeTable(key='attributes',
                                   checkbox=True,
                                   nameEditable=False,
                                   showTypes=True,
                                   types=self.acceptedTypes(),
                                   options=None)
        return factory.getEditor()

    def injectEditor(self, editor: AbsOperationEditor) -> None:
        editor.setSizeHint(500, 600)
        # Set frame model
        editor.attributes.setSourceFrameModel(FrameModel(editor, self.shapes[0]))

    @staticmethod
    def minInputNumber() -> int:
        return 1

    @staticmethod
    def maxInputNumber() -> int:
        return 1

    @staticmethod
    def minOutputNumber() -> int:
        return 1

    @staticmethod
    def maxOutputNumber() -> int:
        return -1


export = MinMaxScaler, StandardScaler


class _RangeDelegate(QStyledItemDelegate):
    def createEditor(self, parent: QWidget, option, index: QModelIndex) -> QWidget:
        editor = QLineEdit(parent=parent)
        editor.setValidator(NumericListValidator(float_int=float, parent=parent))
        return editor

    def setEditorData(self, editor: QLineEdit, index: QModelIndex) -> None:
        dataToSet: Optional[Tuple[float, float]] = index.data(Qt.EditRole)
        if dataToSet:
            editor.setText('{:G}  {:G}'.format(dataToSet[0], dataToSet[1]))
        else:
            editor.setText('')

    def setModelData(self, editor: QLineEdit, model: QAbstractItemModel, index: QModelIndex) -> None:
        rangeText: str = editor.text().strip()
        floatList: List[str] = splitString(rangeText, ' ')[:2]
        if not all(map(isFloat, floatList)) or len(floatList) != 2:
            d = None
        else:
            d = (float(floatList[0]), float(floatList[1]))
        model.setData(index, d, Qt.EditRole)

    def displayText(self, value: Tuple[float, float], locale) -> str:
        return '[{:G}, {:G}]'.format(*value)
