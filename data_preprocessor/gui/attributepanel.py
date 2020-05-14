from PySide2.QtCharts import QtCharts
from PySide2.QtCore import Slot
from PySide2.QtWidgets import QWidget, QVBoxLayout, QHeaderView, QTableView

from data_preprocessor.gui.frame import FrameModel, AttributeTableModel
from data_preprocessor.gui.workbench import WorkbenchModel


class AttributePanel(QWidget):

    def __init__(self, workbench: WorkbenchModel, parent: QWidget = None):
        super().__init__(parent)
        self._workbench: WorkbenchModel = workbench
        self._currentFrameIndex: int = -1
        self._attributeModel: AttributeTableModel = None

        self._attributeTable = QTableView(self)
        section2 = QWidget(self)
        section3 = QtCharts.QChartView(self)

        layout = QVBoxLayout()
        layout.addWidget(self._attributeTable, 2)
        layout.addWidget(section2, 1)
        layout.addWidget(section3, 3)
        self.setLayout(layout)

    @Slot(int)
    def selectionChanged(self, frameIndex: int) -> None:
        if 0 <= frameIndex <= self._workbench.rowCount():
            self._currentFrameIndex = frameIndex
            if not self._attributeModel:
                # Create model the first time
                self._attributeModel = AttributeTableModel(self, True, True)
            frameModel = self._workbench.getDataframeModelByIndex(frameIndex)
        else:
            self._currentFrameIndex = -1
            frameModel = FrameModel(self)
        # Replace frame model
        self._attributeModel.setSourceModel(frameModel)
        # If model is not set in view yet
        if self._attributeTable.model() is not self._attributeModel:
            self._attributeTable.setModel(self._attributeModel)
            hh = self._attributeTable.horizontalHeader()
            hh.resizeSection(0, 10)
            hh.setSectionResizeMode(0, QHeaderView.Fixed)
            hh.setSectionResizeMode(1, QHeaderView.Stretch)
            hh.setSectionResizeMode(2, QHeaderView.Fixed)
            hh.setStretchLastSection(False)
            self._attributeTable.setHorizontalHeader(hh)

# class AttributeTableView(QTableView):
#     def mousePressEvent(self, event:QMouseEvent):
#         x = self.columnViewportPosition(0)
#         size = self.columnWidth(0)
#         if x <= event.globalPos().x() <= x+size:
#             self.model().setData(self.model().index())
