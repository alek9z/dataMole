from typing import Iterable, List, Any

import numpy as np
from PySide2.QtCore import Qt, Slot, QRegExp
from PySide2.QtGui import QRegExpValidator
from PySide2.QtWidgets import QWidget, QComboBox, QLineEdit, QCheckBox, QHBoxLayout, QVBoxLayout

from data_preprocessor import data
from data_preprocessor.data.types import Types
from data_preprocessor.gui import AbsOperationEditor
from data_preprocessor.gui.frame import ShapeAttributeNamesListModel
from data_preprocessor.operation.interface import Operation


class MergeValuesOp(Operation):
    """ Merge values of one attribute into a single value """
    Nan = np.nan

    def __init__(self):
        super().__init__()
        self.__attribute: int = None
        self.__values_to_merge: List = list()
        self.__merge_val: Any = None

    def execute(self, df: data.Frame) -> data.Frame:
        # Check if type of attribute is accepted
        if df.shape.col_types[self.__attribute] not in self.acceptedTypes():
            return df
        # If type is accepted proceed
        pd_df = df.getRawFrame().copy()
        pd_df.iloc[:, [self.__attribute]] = pd_df.iloc[:, [self.__attribute]] \
            .replace(to_replace=self.__values_to_merge, value=self.__merge_val, inplace=False)
        return data.Frame(pd_df)

    @staticmethod
    def name() -> str:
        return 'Merge values'

    def info(self) -> str:
        return 'Substitute all specified values in a attribute and substitute them with a single value'

    def acceptedTypes(self) -> List[Types]:
        return [Types.String, Types.Categorical, Types.Numeric]

    def setOptions(self, attribute: int, values_to_merge: List, value: Any) -> None:
        self.__attribute = attribute
        self.__values_to_merge = values_to_merge
        self.__merge_val = value  # could be Nan

    def unsetOptions(self) -> None:
        self.__attribute = None
        self.__values_to_merge = list()
        self.__merge_val = None

    def needsOptions(self) -> bool:
        return True

    def getOptions(self) -> Iterable:
        return self.__values_to_merge, self.__merge_val, self.__attribute, self._shape[0]

    def getEditor(self) -> AbsOperationEditor:
        return _MergeValEditor()

    def hasOptions(self) -> bool:
        return self.__attribute and self.__values_to_merge and self.__merge_val

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


class _MergeValEditor(AbsOperationEditor):
    # TODO: finish this
    def editorBody(self) -> QWidget:
        self.setWindowTitle('Merge values')
        self.__combo_box = QComboBox()
        self.__merge_list_lineedit = QLineEdit()
        self.__merge_value_lineedit = QLineEdit()
        self.__nan_cb = QCheckBox()
        self.__nan_cb.setText('to Nan')
        layoutH = QHBoxLayout()
        layoutH.addWidget(self.__merge_value_lineedit)
        layoutH.addWidget(self.__nan_cb)

        layout = QVBoxLayout()
        layout.addWidget(self.__combo_box)
        layout.addWidget(self.__merge_list_lineedit)
        layout.addLayout(layoutH)

        self.__nan_cb.stateChanged.connect(self.toggleValueEdit)
        self.__combo_box.currentIndexChanged[int].connect(self.toggleValidator)
        body = QWidget(self)
        body.setLayout(layout)
        return body

    @Slot(int)
    def toggleValueEdit(self, state: Qt.CheckState) -> None:
        if state == Qt.Checked:
            self.__merge_value_lineedit.setDisabled(True)
        else:
            self.__merge_value_lineedit.setDisabled(False)

    @Slot(int)
    def toggleValidator(self, index: int) -> None:
        self.__curr_type = self.__input_shape.col_types[index]
        if self.__curr_type == Types.Numeric:
            reg = QRegExp('(\\d+(\\.\\d)?\\d*)(\\,\\s?(\\d+(\\.\\d)?\\d*))*')
        else:
            reg = QRegExp('(.*?)')
        self.__merge_list_lineedit.setValidator(QRegExpValidator(reg, self))

    def getOptions(self) -> Iterable:
        cur_attr = self.__combo_box.currentIndex() if self.__combo_box.currentText() else None
        list_merge = self.__merge_list_lineedit.text()
        list_merge = list_merge.split(', ') if list_merge else list()
        vv = self.__merge_value_lineedit
        if self.__nan_cb.isChecked():
            value = MergeValuesOp.Nan
        else:
            value = vv.text() if vv.text() else None
        return cur_attr, list_merge, value

    def setOptions(self, values_to_merge: List, merge_val: Any, attribute: int,
                   input_shape: data.Shape) -> None:
        self.__input_shape = input_shape
        self.__combo_box.setModel(ShapeAttributeNamesListModel(input_shape, self))
        if values_to_merge:
            self.__merge_list_lineedit.setText(''.join([str(e) for e in values_to_merge]))
        if merge_val is not None:
            if merge_val == MergeValuesOp.Nan:
                self.__nan_cb.setChecked(True)
                self.__nan_cb.stateChanged.emit(self.__nan_cb.checkState())
            else:
                self.__merge_value_lineedit.setText(str(merge_val))
        if attribute is not None:
            self.__combo_box.setCurrentIndex(attribute)
            self.__curr_type = input_shape.col_types[attribute]
        else:
            self.__combo_box.setCurrentIndex(0)


export = MergeValuesOp