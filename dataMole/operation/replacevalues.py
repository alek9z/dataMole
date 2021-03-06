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

from typing import Iterable, List, Any, Tuple, Dict, Optional

import numpy as np
import prettytable as pt
from PySide2.QtWidgets import QHeaderView

from dataMole import data, flogging
from dataMole import exceptions as exp
from dataMole.data.types import Types, Type
from dataMole.gui.editor import OptionsEditorFactory, OptionValidatorDelegate, \
    AbsOperationEditor
from dataMole.gui.mainmodels import FrameModel
from dataMole.operation.interface.graph import GraphOperation
from dataMole.operation.utils import ManyMixedListsValidator, MixedListValidator, splitString, \
    parseNan, joinList, isFloat


def floatList(values: List, invalid: str) -> List:
    """
    Converts a list of values into float values if possible.

    :param values: values to convert
    :param invalid: {'drop', 'nan', 'ignore'}.
        - 'drop': invalid float values are dropped
        - 'nan': invalid floats are set to np.nan
        - 'ignore': invalid values are left untouched. May results in a list of mixed type

    :return: if invalid is 'drop' or 'nan' returns a list of floats, otherwise it may return a
        list of mixed type

    """
    floatValues = list()
    for el in values:
        if isFloat(el):
            floatValues.append(float(el))
        elif invalid == 'ignore':
            floatValues.append(el)
        elif invalid == 'nan':
            floatValues.append(np.nan)
    return floatValues


class ReplaceValues(GraphOperation, flogging.Loggable):
    """ Merge values of one attribute into a single value """
    Nan = np.nan

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # { col: ([ [vala1, vala2], [valb1, valb2] ], [replacea, replaceb])}
        self.__attributes: Dict[int, Tuple[List[List], List[Any]]] = dict()
        self.__invertedReplace: bool = False

    def logOptions(self) -> str:
        columns = self.shapes[0].colNames
        tt = pt.PrettyTable(field_names=['Column', 'Replaced sets'])
        for a, opts in self.__attributes.items():
            values, rep = opts
            pValues = '\n'.join(['{{{:s}}} -> {}'.format(', '.join(map(str, v)), r)
                                 for v, r in zip(values, rep)])
            tt.add_row([columns[a], pValues])
        inverted: str = '\nInverted selection: {:b}'.format(self.__invertedReplace)
        tt.align = 'l'
        return tt.get_string(vrules=pt.ALL, border=True) + inverted

    def execute(self, df: data.Frame) -> data.Frame:
        pd_df = df.getRawFrame().copy(True)
        for c, colOptions in self.__attributes.items():
            for valueList, replaceVal in zip(*colOptions):
                if self.__invertedReplace:
                    valuesToReplace: List = pd_df.iloc[:, c].unique().tolist()
                    for a in valueList:
                        try:
                            valuesToReplace.remove(a)
                        except ValueError:
                            pass  # Value not in list (ignore)
                else:
                    valuesToReplace = valueList
                pd_df.iloc[:, c] = pd_df.iloc[:, c].replace(to_replace=valuesToReplace,
                                                            value=replaceVal,
                                                            inplace=False)
        return data.Frame(pd_df)

    def getOutputShape(self) -> Optional[data.Shape]:
        if self.hasOptions() and self.shapes[0] is not None:
            return self.shapes[0]
        return None

    @staticmethod
    def name() -> str:
        return 'ReplaceValues'

    @staticmethod
    def shortDescription() -> str:
        return 'Substitute all specified values in a attribute and substitute them with a single value'

    def acceptedTypes(self) -> List[Type]:
        return [Types.String, Types.Ordinal, Types.Nominal, Types.Numeric]

    def setOptions(self, table: Dict[int, Dict[str, str]], inverted: bool) -> None:
        if not table:
            raise exp.OptionValidationError([('nooptions', 'Error: no attributes are selected')])
        options: Dict[int, Tuple[List[List], List]] = dict()
        for c, opt in table.items():
            type_c = self.shapes[0].colTypes[c]
            values: str = opt.get('values', None)
            replace: str = opt.get('replace', None)
            if not values or not replace:
                raise exp.OptionValidationError(
                    [('incompleteoptions', 'Error: options are not set at row {:d}'.format(c))])
            lists: List[str] = splitString(values, ';')
            replace: List[str] = splitString(replace, ';')
            if not lists or not replace:
                raise exp.OptionValidationError(
                    [('incompleteoptions', 'Error: options are not set at row '
                                           '{:d}'.format(c))])
            if len(lists) != len(replace):
                raise exp.OptionValidationError(
                    [('wrongnum', 'Error: number of intervals is not equal to '
                                  'the number of values to replace at row {:d}'
                      .format(c))])
            parsedValues: List[List[str]] = [splitString(s, ' ') for s in lists]
            if type_c == Types.Numeric:
                if not all(map(isFloat, replace)):
                    err = ('numericinvalid', 'Error: list of values to replace contains non '
                                             'numeric value at row {:d}, but selected attribute '
                                             'is numeric'.format(c))
                    raise exp.OptionValidationError([err])
                replace: List[float] = [float(x) for x in replace]
                parsedValues: List[List[float]] = [floatList(l, invalid='drop') for l in parsedValues]
            else:
                # If type is not numeric everything will be treated as string
                replace: List = parseNan(replace)
                parsedValues: List[List] = [parseNan(a) for a in parsedValues]
            # Save parsed options for this column
            options[c] = (parsedValues, replace)
        self.__attributes = options
        self.__invertedReplace = inverted

    def unsetOptions(self) -> None:
        self.__attributes = dict()

    def needsOptions(self) -> bool:
        return True

    def getOptions(self) -> Iterable:
        options = dict()
        options['table'] = dict()
        for c, opt in self.__attributes.items():
            # Convert every internal list into a string separated by spaces
            s: List[str] = list(map(lambda x: joinList(x, sep=' '), opt[0]))
            options['table'][c] = {
                'values': joinList(s, sep='; '),
                'replace': joinList(opt[1], sep='; ')
            }
        options['inverted'] = self.__invertedReplace
        return options

    def getEditor(self) -> AbsOperationEditor:
        factory = OptionsEditorFactory()
        options = {
            'values': ('Values', OptionValidatorDelegate(ManyMixedListsValidator()), None),
            'replace': ('Replace with', OptionValidatorDelegate(MixedListValidator()), None)
        }
        factory.initEditor()
        factory.withAttributeTable('table', True, False, True, options, self.acceptedTypes())
        factory.withCheckBox('Invert values selection', 'inverted')
        return factory.getEditor()

    def injectEditor(self, editor: AbsOperationEditor) -> None:
        # Set frame model
        editor.table.setSourceFrameModel(FrameModel(editor, self.shapes[0]))
        # Stretch new section
        editor.table.tableView.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        editor.table.tableView.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)

    def hasOptions(self) -> bool:
        return self.__attributes and self.__invertedReplace is not None

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


export = ReplaceValues
