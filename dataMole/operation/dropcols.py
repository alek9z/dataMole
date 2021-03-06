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

from typing import List, Dict, Optional

import prettytable as pt

from dataMole import data, exceptions as exp, flogging
from dataMole.gui.editor import AbsOperationEditor, OptionsEditorFactory
from dataMole.gui.mainmodels import FrameModel
from dataMole.operation.interface.graph import GraphOperation


class DropColumns(GraphOperation, flogging.Loggable):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # List of selected attributes by column name
        self.__selected: List[int] = list()

    def logOptions(self) -> Optional[str]:
        tt = pt.PrettyTable(field_names=['Columns to drop'])
        columns = self.shapes[0].colNames
        for a in self.__selected:
            tt.add_row([columns[a]])
        return tt.get_string(border=True, vrules=pt.ALL)

    def execute(self, df: data.Frame) -> data.Frame:
        df = df.getRawFrame()
        return data.Frame(df.drop(columns=df.columns[[self.__selected]]))

    @staticmethod
    def name() -> str:
        return 'DropColumns'

    def setOptions(self, selected: Dict[int, None]) -> None:
        if not selected:
            raise exp.OptionValidationError([('e', 'Error: no attribute is selected')])
        self.__selected = list(selected.keys())

    @staticmethod
    def shortDescription() -> str:
        return 'Remove entire columns from dataframe'

    def hasOptions(self) -> bool:
        return bool(self.__selected)

    def unsetOptions(self) -> None:
        self.__selected = list()

    def needsOptions(self) -> bool:
        return True

    def getOptions(self) -> Dict[str, Dict[int, None]]:
        return {'selected': {k: None for k in self.__selected}}

    def getEditor(self) -> AbsOperationEditor:
        factory = OptionsEditorFactory()
        factory.initEditor()
        factory.withAttributeTable(key='selected', checkbox=True, nameEditable=False, showTypes=True,
                                   options=None, types=self.acceptedTypes())
        return factory.getEditor()

    def injectEditor(self, editor: 'AbsOperationEditor') -> None:
        editor.selected.setSourceFrameModel(FrameModel(editor, self.shapes[0]))

    def getOutputShape(self) -> Optional[data.Shape]:
        if not self.hasOptions():
            return None
        s = self.shapes[0].clone()
        s.colNames = [n for i, n in enumerate(s.colNames) if i not in self.__selected]
        s.colTypes = [t for i, t in enumerate(s.colTypes) if i not in self.__selected]
        return s

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


export = DropColumns
