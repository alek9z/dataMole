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

import os
from typing import Iterable, List, Dict, Set, Optional

import pandas as pd
from PySide2.QtCore import Slot, Qt, Signal, QThread
from PySide2.QtGui import QIntValidator
from PySide2.QtWidgets import QVBoxLayout, QHBoxLayout, QCheckBox, QLineEdit, QLabel, QFileDialog, \
    QPushButton, QButtonGroup, QRadioButton, QWidget

from dataMole import data, exceptions as exp
from dataMole.data import Frame
from dataMole.gui.editor import OptionsEditorFactory, AbsOperationEditor
from dataMole.gui.mainmodels import FrameModel, SearchableAttributeTableWidget
from dataMole.gui.widgets.waitingspinnerwidget import QtWaitingSpinner
from dataMole.operation.interface.operation import Operation


class CsvLoader(Operation):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__file: str = None
        self.__separator: str = None
        self.__wName: str = None
        self.__splitByRowN: int = None
        self.__selectedColumns: Set[int] = set()

    def hasOptions(self) -> bool:
        return self.__file is not None and self.__separator is not None and self.__wName

    def execute(self) -> None:
        if not self.hasOptions():
            raise exp.InvalidOptions('Options are not set')
        pd_df = pd.read_csv(self.__file, sep=self.__separator,
                            index_col=False,
                            usecols=self.__selectedColumns,
                            chunksize=self.__splitByRowN)
        if self.__splitByRowN is not None:
            # pd_df is a chunk iterator
            for i, chunk in enumerate(pd_df):
                name: str = self.__wName + '_{:d}'.format(i)
                self._workbench.setDataframeByName(name, data.Frame(chunk))
                # TOCHECK: this does not set a parent for the FrameModel (since workbench lives in
                #  different thread)
        else:
            # entire dataframe is read
            self._workbench.setDataframeByName(self.__wName, data.Frame(pd_df))

    @staticmethod
    def name() -> str:
        return 'Load CSV'

    @staticmethod
    def shortDescription() -> str:
        return 'Loads a dataframe from a CSV'

    def longDescription(self) -> str:
        return 'By selecting \'Split by rows\' you can load a CSV file as multiple smaller dataframes ' \
               'each one with the specified number of rows. This allows to load big files which are ' \
               'too memory consuming to load with pandas'

    def setOptions(self, file: str, separator: str, name: str, splitByRow: int,
                   selectedCols: Set[int]) -> None:
        errors = list()
        if not name:
            errors.append(('nameError', 'Error: a valid name must be specified'))
        if not selectedCols:
            errors.append(('noSelection', 'Error: at least 1 attribute must be selected'))
        if errors:
            raise exp.OptionValidationError(errors)
        self.__file = file
        self.__separator = separator
        self.__wName = name
        self.__splitByRowN = splitByRow if (splitByRow and splitByRow > 0) else None
        self.__selectedColumns = selectedCols

    def needsOptions(self) -> bool:
        return True

    def getOptions(self) -> Iterable:
        return self.__file, self.__separator, self.__wName, self.__splitByRowN, self.__selectedColumns

    def getEditor(self) -> 'AbsOperationEditor':
        return LoadCSVEditor()


class CsvWriter(Operation):
    def __init__(self, frameName: str = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__frame_name: str = frameName
        self.__path: str = None
        self.__sep: str = ','
        self.__nan_rep: str = 'nan'
        self.__float_format: str = '%g'
        self.__header: bool = True
        self.__index: bool = True
        self.__selected_columns: List[str] = list()
        self.__date_format: str = '%Y-%m-%d %H:%M:%S'
        self.__decimal: str = '.'

    @staticmethod
    def name() -> str:
        return 'Write CSV'

    def execute(self) -> None:
        df: pd.DataFrame = self._workbench.getDataframeModelByName(self.__frame_name).frame.getRawFrame()
        df.to_csv(self.__path, sep=self.__sep, na_rep=self.__nan_rep,
                  float_format=self.__float_format, columns=self.__selected_columns,
                  header=self.__header, index=self.__index, date_format=self.__date_format,
                  decimal=self.__decimal)

    @staticmethod
    def shortDescription() -> str:
        return 'Load a dataframe from CSV file'

    def getEditor(self) -> 'AbsOperationEditor':
        factory = OptionsEditorFactory()
        factory.initEditor(subclass=WriteEditorBase)
        factory.withComboBox('Frame to write', 'frame', False, model=self.workbench)
        factory.withFileChooser(key='file', label='Choose a file', extensions='Csv (*.csv)', mode='save')
        factory.withAttributeTable(key='sele', checkbox=True, nameEditable=False, showTypes=True,
                                   options=None, types=self.acceptedTypes())
        factory.withTextField('Separator', 'sep')
        factory.withTextField('Nan repr', 'nan')
        factory.withTextField('Float format', 'ffloat')
        factory.withTextField('Decimal', 'decimal')
        factory.withCheckBox('Write column names', 'header')
        factory.withCheckBox('Write index values', 'index')
        factory.withComboBox('Datetime format', 'date', True, strings=['%Y-%m-%d %H:%M:%S',
                                                                       '%Y-%m-%d', '%H:%M:%S'])
        return factory.getEditor()

    def injectEditor(self, editor: 'AbsOperationEditor') -> None:
        # Make editor react to frame change
        editor.frame.currentTextChanged.connect(editor.inputFrameChanged)
        ct = editor.frame.currentText()
        if ct:
            editor.inputFrameChanged(ct)

    def setOptions(self, frame: str, file: str, sele: Dict[int, None], sep: str, nan: str, ffloat: str,
                   decimal: str, header: bool, index: bool, date: str) -> None:
        errors = list()
        if frame not in self.workbench.names:
            errors.append(('e1', 'Error: frame name is not valid'))
        if not sele:
            errors.append(('e2', 'Error: no attribute to write are selected'))
        nan = parseUnicodeStr(nan)
        sep = parseUnicodeStr(sep)
        if not sep:
            errors.append(('es1', 'Error: a separator char is required'))
        elif len(sep) > 1:
            errors.append(('es2', 'Error: separator must be a single character'))
        if not decimal:
            errors.append(('na1', 'Error: a decimal separator is required'))
        elif len(decimal) > 1:
            errors.append(('na2', 'Error: decimal separator must be a single character'))
        if not date:
            errors.append(('d1', 'Error: datetime format must be specified'))
        if not file:
            errors.append(('f1', 'Error: no output file specified'))
        if errors:
            raise exp.OptionValidationError(errors)

        # Save selected column names
        columns: List[str] = self.workbench.getDataframeModelByName(frame).frame.colnames

        self.__frame_name = frame
        self.__path = file
        self.__selected_columns = [columns[i] for i in sele.keys()]
        self.__date_format = date
        self.__sep = sep
        self.__nan_rep = nan
        self.__float_format = ffloat
        self.__decimal = decimal
        self.__index = index
        self.__header = header

    def getOptions(self) -> Iterable:
        return {
            'frame': self.__frame_name,
            'file': self.__path,
            'sele': {i: None for i in self.__selected_columns},
            'date': self.__date_format,
            'sep': self.__sep,
            'nan': self.__nan_rep,
            'ffloat': self.__float_format,
            'decimal': self.__decimal,
            'header': self.__header,
            'index': self.__index
        }

    def needsOptions(self) -> bool:
        return True


def parseUnicodeStr(s: str) -> str:
    return bytes(s, 'utf-8').decode('unicode_escape')


class WriteEditorBase(AbsOperationEditor):
    """ Base editor class for write csv operation """

    @Slot(str)
    def inputFrameChanged(self, name: str) -> None:
        frame: 'FrameModel' = self.workbench.getDataframeModelByName(name)
        self.sele.setSourceFrameModel(frame)


class LoadCSVEditor(AbsOperationEditor):
    """ Editor for loading CSV """

    def editorBody(self) -> QWidget:
        class MyWidget(QWidget):
            def __init__(self, parent):
                super().__init__(parent)
                self.buttons_id_value = {
                    1: ('comma', ','),
                    2: ('space', '\b'),
                    3: ('tab', '\t'),
                    4: ('semicolon', ';')
                }
                self.separator = QButtonGroup()
                lab = QLabel()
                lab.setText('Choose a separator:')
                for bid, value in self.buttons_id_value.items():
                    self.separator.addButton(QRadioButton(value[0]), id=bid)
                self.separator.setExclusive(True)
                self.default_button = self.separator.button(1)
                button_layout = QHBoxLayout()
                for button in self.separator.buttons():
                    button_layout.addWidget(button)
                self.default_button.click()

                openFileChooser = QPushButton('Choose')
                fileChooser = QFileDialog(self, 'Open csv', str(os.getcwd()), 'Csv (*.csv *.tsv *.dat)')
                fileChooser.setFileMode(QFileDialog.ExistingFile)
                self.filePath = QLineEdit()
                openFileChooser.released.connect(fileChooser.show)
                fileChooser.fileSelected.connect(self.filePath.setText)
                self.filePath.textChanged.connect(self.checkFileExists)
                nameLabel = QLabel('Select a name:', self)
                self.nameField = QLineEdit(self)
                self.nameErrorLabel = QLabel(self)

                self.file_layout = QVBoxLayout()
                fileChooserLayout = QHBoxLayout()
                nameRowLayout = QHBoxLayout()
                fileChooserLayout.addWidget(openFileChooser)
                fileChooserLayout.addWidget(self.filePath)
                nameRowLayout.addWidget(nameLabel)
                nameRowLayout.addWidget(self.nameField)
                self.fileErrorLabel = QLabel(self)
                self.file_layout.addLayout(fileChooserLayout)
                self.file_layout.addWidget(self.fileErrorLabel)
                self.file_layout.addLayout(nameRowLayout)
                self.file_layout.addWidget(self.nameErrorLabel)
                self.fileErrorLabel.hide()
                self.nameErrorLabel.hide()
                self.tablePreview = SearchableAttributeTableWidget(self, True)
                self.tableSpinner = QtWaitingSpinner(self.tablePreview, centerOnParent=True,
                                                     disableParentWhenSpinning=True)
                self.nameField.textEdited.connect(self.nameErrorLabel.hide)

                # Split file by row
                splitRowLayout = QHBoxLayout()
                self.checkSplit = QCheckBox('Split file by rows', self)
                self.numberRowsChunk = QLineEdit(self)
                self.numberRowsChunk.setPlaceholderText('Number of rows per chunk')
                self.numberRowsChunk.setValidator(QIntValidator(self))
                splitRowLayout.addWidget(self.checkSplit)
                splitRowLayout.addWidget(self.numberRowsChunk)
                self.checkSplit.stateChanged.connect(self.toggleSplitRows)

                layout = QVBoxLayout()
                layout.addLayout(self.file_layout)
                layout.addWidget(lab)
                layout.addLayout(button_layout)
                layout.addLayout(splitRowLayout)
                layout.addWidget(QLabel('Preview'))
                layout.addWidget(self.tablePreview)
                self.setLayout(layout)

                self.filePath.textChanged.connect(self.loadPreview)
                self.separator.buttonClicked.connect(self.loadPreview)

            @Slot(object)
            def loadPreview(self) -> None:
                if not os.path.isfile(self.filePath.text()):
                    return

                class WorkerThread(QThread):
                    resultReady = Signal(Frame)

                    def __init__(self, path: str, separ: str, parent=None):
                        super().__init__(parent)
                        self.__path = path
                        self.__sep = separ

                    def run(self):
                        header = pd.read_csv(self.__path, sep=self.__sep, index_col=False, nrows=0)
                        self.resultReady.emit(Frame(header))

                sep: int = self.separator.checkedId()
                sep_s: str = self.buttons_id_value[sep][1] if sep != -1 else None
                assert sep_s is not None

                # Async call to load header
                worker = WorkerThread(path=self.filePath.text(), separ=sep_s, parent=self)
                worker.resultReady.connect(self.onPreviewComputed)
                worker.finished.connect(worker.deleteLater)
                self.tableSpinner.start()
                worker.start()

            @Slot(Frame)
            def onPreviewComputed(self, header: Frame):
                self.tablePreview.setSourceFrameModel(FrameModel(self, header))
                self.tablePreview.model().setAllChecked(True)
                self.tableSpinner.stop()

            @Slot(str)
            def checkFileExists(self, path: str) -> None:
                file_exists = os.path.isfile(path)
                if not file_exists:
                    self.fileErrorLabel.setText('File does not exists!')
                    self.fileErrorLabel.setStyleSheet('color: red')
                    self.filePath.setToolTip('File does not exists!')
                    self.filePath.setStyleSheet('border: 1px solid red')
                    # self.file_layout.addWidget(self.fileErrorLabel)
                    self.parentWidget().disableOkButton()
                    self.fileErrorLabel.show()
                else:
                    # self.file_layout.removeWidget(self.fileErrorLabel)
                    self.fileErrorLabel.hide()
                    self.filePath.setStyleSheet('')
                    self.parentWidget().enableOkButton()
                    if not self.nameField.text():
                        name: str = os.path.splitext(os.path.basename(path))[0]
                        self.nameField.setText(name)

            @Slot(Qt.CheckState)
            def toggleSplitRows(self, state: Qt.CheckState) -> None:
                if state == Qt.Checked:
                    self.numberRowsChunk.setEnabled(True)
                else:
                    self.numberRowsChunk.setDisabled(True)

            def showNameError(self, msg: str) -> None:
                self.nameErrorLabel.setText(msg)
                self.nameErrorLabel.setStyleSheet('color: red')
                self.nameErrorLabel.show()

        self.mywidget = MyWidget(self)
        self.errorHandlers['nameError'] = self.mywidget.showNameError
        return self.mywidget

    def getOptions(self) -> Iterable:
        path: str = self.mywidget.filePath.text()
        sep: int = self.mywidget.separator.checkedId()
        path = path if path else None
        sep_s: str = self.mywidget.buttons_id_value[sep][1] if sep != -1 else None
        chunksize = int(self.mywidget.numberRowsChunk.text()) if self.mywidget.checkSplit.isChecked() \
            else None
        varName: str = self.mywidget.nameField.text()
        selectedColumns: Set[int] = self.mywidget.tablePreview.model().checked
        return path, sep_s, varName, chunksize, selectedColumns

    def setOptions(self, path: Optional[str], sep: Optional[str], name: Optional[str],
                   splitByRow: Optional[int], selectedColumns: Set[int]) -> None:
        self.mywidget.filePath.setText('')
        self.mywidget.default_button.click()
        self.mywidget.nameField.setText('')
        self.mywidget.checkSplit.setChecked(False)
        self.mywidget.toggleSplitRows(self.mywidget.checkSplit.checkState())
