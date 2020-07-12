import copy
from collections import OrderedDict
from enum import Enum
from typing import Iterable, List, Dict, Optional, Tuple

import numpy as np
import pandas as pd
import prettytable as pt
import sklearn.preprocessing as skp
from PySide2.QtGui import QIntValidator
from PySide2.QtWidgets import QHeaderView

from data_preprocessor import data
from data_preprocessor import flogging
from data_preprocessor.data.types import Types, Type
from data_preprocessor.gui.editor import OptionsEditorFactory, OptionValidatorDelegate, \
    AbsOperationEditor
from data_preprocessor.gui.mainmodels import FrameModel
from data_preprocessor.operation.interface.exceptions import OptionValidationError
from data_preprocessor.operation.interface.graph import GraphOperation
from data_preprocessor.operation.utils import NumericListValidator, MixedListValidator, splitString, \
    joinList


class BinStrategy(Enum):
    Uniform = 'uniform'
    Quantile = 'quantile'
    Kmeans = 'kmeans'


class BinsDiscretizer(GraphOperation, flogging.Loggable):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__strategy: BinStrategy = BinStrategy.Uniform
        self.__attributes: Dict[int, int] = dict()
        self.__dropTransformed: bool = True

    def __logExecution(self, columns: List[str], binEdges: Dict[int, List[float]]) -> None:
        optPt = pt.PrettyTable(field_names=['Option', 'Value'])
        optPt.add_row(['Strategy', self.__strategy.value])
        optPt.add_row(['Drop transformed', self.__dropTransformed])

        binsPt = pt.PrettyTable(field_names=['Column', 'K', 'Computed bins', 'Actual K'])
        for i, k in self.__attributes.items():
            iEdges = binEdges[i]
            binsPt.add_row([columns[i], k, ', '.join(['{:G}'.format(e) for e in iEdges]), len(iEdges)])

        self._logOptionsString = optPt.get_string(border=True, vrules=pt.ALL)
        self._logExecutionString = binsPt.get_string(border=True, vrules=pt.ALL)

    def execute(self, df: data.Frame) -> data.Frame:
        frame = copy.deepcopy(df)
        sortedAttr = OrderedDict(sorted(self.__attributes.items(), key=lambda t: t[0]))
        columnList = list(sortedAttr.keys())
        binsList = list(sortedAttr.values())
        f = frame.getRawFrame()
        # Operation ignores nan values
        nanRows = f.iloc[:, columnList].isnull()
        # For every column, transform every non-nan row
        columns = f.columns
        edges: Dict[int, List[float]] = dict()
        for col, k in zip(columnList, binsList):
            nr = nanRows.loc[:, columns[col]]
            discretizer = skp.KBinsDiscretizer(n_bins=k, encode='ordinal',
                                               strategy=self.__strategy.value)
            result = discretizer.fit_transform(f.iloc[(~nr).to_list(), [col]]).astype(str)
            if self.__dropTransformed:
                f.iloc[(~nr).to_list(), [col]] = result
                f.iloc[:, col] = f.iloc[:, col].astype('category')
            else:
                colName: str = self.shapes[0].colNames[col] + '_discretized'
                f.loc[:, colName] = np.nan
                f.loc[(~nr).to_list(), [colName]] = result
                f.loc[:, colName] = f.loc[:, colName].astype('category')
            edges[col] = discretizer.bin_edges_[0].tolist()
        # Log what has been done
        self.__logExecution(columns, edges)
        return data.Frame(f)

    def acceptedTypes(self) -> List[Type]:
        return [Types.Numeric]

    @staticmethod
    def name() -> str:
        return 'KBinsDiscretizer'

    def shortDescription(self) -> str:
        return 'Discretize numeric values into equal sized bins'

    def hasOptions(self) -> bool:
        return self.__attributes and self.__strategy is not None and self.__dropTransformed is not None

    def unsetOptions(self) -> None:
        self.__attributes = dict()

    def needsOptions(self) -> bool:
        return True

    def getOptions(self) -> Iterable:
        options = dict()
        options['attributes'] = dict()
        for r, bins in self.__attributes.items():
            options['attributes'][r] = {'bins': bins}
        options['strategy'] = self.__strategy
        options['drop'] = self.__dropTransformed
        return options

    def setOptions(self, attributes: Dict[int, Dict[str, str]], strategy: BinStrategy, drop: bool) -> \
            None:
        # Validate options
        def isPositiveInteger(x):
            try:
                y = int(x)
            except ValueError:
                return False
            else:
                if y > 1:
                    return True
                return False

        errors = list()
        if not attributes:
            errors.append(('nosel', 'Error: At least one attribute should be selected'))
        for r, options in attributes.items():
            bins = options.get('bins', None)
            if not bins:
                errors.append(('nooption', 'Error: Number of bins must be set at row {:d}'.format(r)))
            elif not isPositiveInteger(bins):
                errors.append(('binsNotInt', 'Error: Number of bins must be > 1 at row {:d}'.format(r)))
        if strategy is None:
            errors.append(('missingStrategy', 'Error: Strategy must be set'))
        if errors:
            raise OptionValidationError(errors)
        # Clear attributes
        self.__attributes = dict()
        # Set options
        for r, options in attributes.items():
            k = int(options['bins'])
            self.__attributes[r] = k
        self.__strategy = strategy
        self.__dropTransformed = drop

    def getEditor(self) -> AbsOperationEditor:
        factory = OptionsEditorFactory()
        factory.initEditor()
        factory.withAttributeTable('attributes', True, False, True,
                                   {
                                       'bins': (
                                           'K', OptionValidatorDelegate(QIntValidator(1, 10000000)), None
                                       )}, types=self.acceptedTypes())
        values = [(s.name, s) for s in BinStrategy]
        factory.withRadioGroup('Select strategy:', 'strategy', values)
        factory.withCheckBox('Drop original attributes', 'drop')
        return factory.getEditor()

    def injectEditor(self, editor: 'AbsOperationEditor') -> None:
        editor.inputShapes = self.shapes
        editor.acceptedTypes = self.acceptedTypes()
        # Set frame model
        editor.attributes.setSourceFrameModel(FrameModel(editor, self.shapes[0]))
        # Stretch new section
        editor.attributes.tableView.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

    def getOutputShape(self) -> Optional[data.Shape]:
        if not self.hasOptions() or self.shapes[0] is None:
            return None
        s = self.shapes[0].clone()
        if self.__dropTransformed:
            # Shape does not change
            for col in self.__attributes.keys():
                s.colTypes[col] = Types.Nominal
        else:
            for col in self.__attributes.keys():
                colName: str = self.shapes[0].colNames[col] + '_discretized'
                s.colNames.append(colName)  # new column with suffix
                s.colTypes.append(Types.Nominal)
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


class RangeDiscretizer(GraphOperation, flogging.Loggable):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # { col: (edges, labels) }
        self.__attributes: Dict[int, Tuple[List[float], List[str]]] = dict()
        self.__dropTransformed: bool = True

    def logOptions(self) -> None:
        columns = self.shapes[0].colNames
        tt = pt.PrettyTable(field_names=['Column', 'Ranges', 'Labels'])
        for i, opts in self.__attributes.items():
            tt.add_row([columns[i],
                        ', '.join(
                            ['({:G}, {:G}]'.format(a, b) for a, b in zip(opts[0], opts[0][1:])]),
                        ', '.join(opts[1])])
        drop: str = '\nDrop transformed: {}'.format(self.__dropTransformed)

        return tt.get_string(border=True, vrules=pt.ALL) + drop

    def execute(self, df: data.Frame) -> data.Frame:
        f = df.getRawFrame().copy(True)
        columns = f.columns.to_list()
        for c, o in self.__attributes.items():
            result = pd.cut(f.iloc[:, c], bins=o[0], labels=o[1], duplicates='drop')
            colName: str = columns[c]
            newColName: str = colName if self.__dropTransformed else colName + '_bins'
            f.loc[:, newColName] = result
        return data.Frame(f)

    def getOutputShape(self) -> Optional[data.Shape]:
        if self.shapes[0] is None and not self.hasOptions():
            return None
        s = self.shapes[0].clone()
        if self.__dropTransformed:
            for c in self.__attributes.keys():
                s.colTypes[c] = Types.Ordinal
        else:
            for c in self.__attributes.keys():
                colName: str = s.colNames[c] + '_bins'
                s.colNames.append(colName)
                s.colTypes.append(Types.Ordinal)
        return s

    @staticmethod
    def name() -> str:
        return 'RangeDiscretizer'

    def shortDescription(self) -> str:
        return 'Discretize numeric attributes in user defined ranges'

    def longDescription(self) -> str:
        return '<h4>Table options</h4>' \
               'Bin edges can be specified in the \'Bin edges\' column. Bin edges must be numbers and ' \
               'must be separated by a single space. Bin labels must be specified and their number ' \
               'must be exactly the number of intervals specified, which is the number of edges ' \
               '-1.<br> ' \
               '<em>Example:</em><table><tr>' \
               '    <th>Bin edges</th>' \
               '    <th>Labels</th>' \
               '</tr>' \
               '<tr>' \
               '    <td>1.0 1.5 4 5.1</td>' \
               '    <td>Low Medium High</td> ' \
               '</tr></table>' \
               'In the example bins are set for intervals:<br>(1.0, 1.5], (1.5, 4.0], (4.0, 5.1]' \
               '<h4>Drop attribute</h4>' \
               'It\'s possible to replace the original attribute with the ' \
               'discretization or preserve it, adding the discretized attribute as a new one. In this ' \
               'last case the new attribute will have the same name as the original with \'_bins\' ' \
               'suffix.'

    def acceptedTypes(self) -> List[Type]:
        return [Types.Numeric]

    def hasOptions(self) -> bool:
        return bool(self.__attributes) and self.__dropTransformed is not None

    def unsetOptions(self) -> None:
        self.__attributes: Dict[int, Tuple[List[float], List[str]]] = dict()

    def needsOptions(self) -> bool:
        return True

    def getOptions(self) -> Iterable:
        options = dict()
        options['table'] = dict()
        for row, opt in self.__attributes.items():
            options['table'][row] = {'bins': joinList(opt[0], sep=' '),
                                     'labels': joinList(opt[1], sep=' ')}
            options['drop'] = self.__dropTransformed
        return options

    def getEditor(self) -> AbsOperationEditor:
        factory = OptionsEditorFactory()
        factory.initEditor()
        options = {
            'bins': ('Bin edges', OptionValidatorDelegate(NumericListValidator(float_int=float)), None),
            'labels': ('Labels', OptionValidatorDelegate(MixedListValidator()), None)
        }
        factory.withAttributeTable('table', True, False, True, options, self.acceptedTypes())
        factory.withCheckBox('Drop original columns', 'drop')
        return factory.getEditor()

    def injectEditor(self, editor: 'AbsOperationEditor') -> None:
        editor.inputShapes = self.shapes
        editor.acceptedTypes = self.acceptedTypes()
        # Set frame model
        editor.table.setSourceFrameModel(FrameModel(editor, self.shapes[0]))
        # Stretch new section
        editor.table.tableView.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        editor.table.tableView.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)

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

    def setOptions(self, table: Dict[int, Dict[str, str]], drop: bool) -> None:
        # Validate options
        def isValidEdge(x):
            try:
                float(x)
            except ValueError:
                return False
            else:
                return True

        if not table:
            raise OptionValidationError([('noAttr', 'Error: at least one attribute should be chosen')])
        errors = list()
        options: Dict[int, Tuple[List[float], List[str]]] = dict()
        for row, opts in table.items():
            if not opts.get('bins', None) or not opts.get('labels', None):
                errors.append(('notSet', 'Error: options at row {:d} are not set'.format(row)))
                raise OptionValidationError(errors)
            stringList: str = opts['bins']
            stringEdges: List[str] = splitString(stringList, sep=' ')
            if not all([isValidEdge(v) for v in stringEdges]):
                errors.append(('invalidFloat',
                               'Error: Bin edges are not valid numbers at row {:d}'.format(row)))
            else:
                edges: List[float] = [float(x) for x in stringEdges]
            bins: List[str] = splitString(opts['labels'], sep=' ')
            labNum = len(stringEdges) - 1
            if len(bins) != labNum:
                errors.append(('invalidLabels',
                               'Error: Labels at row {:d} is not equal to the number of intervals '
                               'defined ({:d})'.format(row, labNum)))
            if errors:
                raise OptionValidationError(errors)
            else:
                options[row] = (edges, bins)
        # If everything went well set options
        self.__attributes = options
        self.__dropTransformed = drop


export = [BinsDiscretizer, RangeDiscretizer]
