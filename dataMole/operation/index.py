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

from typing import Iterable, List, Union, Dict

from dataMole import data, flogging
from dataMole import exceptions as exp
from dataMole.data.types import ALL_TYPES, Type, IndexType
from dataMole.gui.editor import AbsOperationEditor, OptionsEditorFactory
from dataMole.gui.mainmodels import FrameModel
from dataMole.operation.interface.graph import GraphOperation


class SetIndex(GraphOperation, flogging.Loggable):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__columns: List[int] = list()

    def execute(self, df: data.Frame) -> data.Frame:
        names = [df.colnames[i] for i in self.__columns]
        f = df.getRawFrame().set_index(names, drop=True, append=False, verify_integrity=False)
        return data.Frame(f)

    @staticmethod
    def name() -> str:
        return 'Set index'

    @staticmethod
    def shortDescription() -> str:
        return 'Sets the column index of a table'

    def acceptedTypes(self) -> List[Type]:
        return ALL_TYPES

    def hasOptions(self) -> bool:
        return bool(self.__columns)

    def setOptions(self, selected: Dict[int, None]) -> None:
        if not selected:
            raise exp.OptionValidationError([('empty', 'Error: at least one column must be selected')])
        self.__columns = list(selected.keys())

    def getOptions(self) -> Iterable:
        return {'selected': {k: None for k in self.__columns}}

    def unsetOptions(self) -> None:
        self.__columns = list()

    def needsOptions(self) -> bool:
        return True

    def getOutputShape(self) -> Union[data.Shape, None]:
        if not self.hasOptions() or not self._shapes[0]:
            return None
        s = self._shapes[0].clone()
        s.index = [s.colNames[i] for i in self.__columns]
        s.indexTypes = [IndexType(s.colTypes[i]) for i in self.__columns]
        s.colNames = [name for i, name in enumerate(s.colNames) if i not in self.__columns]
        s.colTypes = [dtype for i, dtype in enumerate(s.colTypes) if i not in self.__columns]
        return s

    def getEditor(self) -> AbsOperationEditor:
        factory = OptionsEditorFactory()
        factory.initEditor()
        factory.withAttributeTable('selected', True, False, True, None, self.acceptedTypes())
        return factory.getEditor()

    def injectEditor(self, editor: 'AbsOperationEditor') -> None:
        # Set frame model
        editor.selected.setSourceFrameModel(FrameModel(editor, self.shapes[0]))

    @staticmethod
    def isOutputShapeKnown() -> bool:
        return True

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


class ResetIndex(GraphOperation, flogging.Loggable):
    def execute(self, df: data.Frame) -> data.Frame:
        f = df.getRawFrame()
        columns = set(f.columns.to_list())
        indexNames = set(f.index.names)
        conflicts = columns & indexNames
        if conflicts:
            # There are columns named as index columns. Rename index
            f.index = f.index.set_names([col + '_index' for col in conflicts], level=conflicts if len(
                indexNames) > 1 else None)
        # Reset index adding indexes as columns. Now there cannot be naming conflicts
        f = f.reset_index(drop=False)
        return data.Frame(f)

    @staticmethod
    def name() -> str:
        return 'Reset index'

    @staticmethod
    def shortDescription() -> str:
        return 'Sets a default numeric index on the dataframe. The old indexes are re-inserted in the ' \
               'dataframe as columns'

    def acceptedTypes(self) -> List[Type]:
        return ALL_TYPES

    def hasOptions(self) -> bool:
        return True

    def setOptions(self, *args, **kwargs) -> None:
        pass

    def getOptions(self) -> Iterable:
        return tuple()

    def unsetOptions(self) -> None:
        pass

    def needsOptions(self) -> bool:
        return False

    def getEditor(self) -> AbsOperationEditor:
        pass

    @staticmethod
    def isOutputShapeKnown() -> bool:
        return True

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


export = [SetIndex, ResetIndex]
