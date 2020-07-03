from typing import Any, Set, List

import pandas as pd
from PySide2.QtCharts import QtCharts
from PySide2.QtCore import Qt, QAbstractItemModel, Slot, QAbstractTableModel, QModelIndex, \
    QSortFilterProxyModel, QMargins, QPointF, QStringListModel
from PySide2.QtGui import QFont
from PySide2.QtWidgets import QWidget, QComboBox, QLineEdit, QLabel, QHBoxLayout, QVBoxLayout, \
    QCheckBox, QSplitter, QTableView, QHeaderView, QPushButton, QSizePolicy

from data_preprocessor.data.types import Types, Type
from data_preprocessor.gui.charts.views import InteractiveChartView
from data_preprocessor.gui.mainmodels import SearchableAttributeTableWidget, AttributeProxyModel, \
    AttributeTableModel, FrameModel, BooleanBoxDelegate
from data_preprocessor.gui.workbench import WorkbenchModel
from data_preprocessor.utils import safeDelete


# INDEX TABLE

class SearchableTableWidget(QWidget):
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.tableView = IndexTableView(parent=self)

        self.searchBar = QLineEdit(self)
        self.searchBar.setPlaceholderText('Search')
        searchLabel = QLabel('Index search', self)
        searchLayout = QHBoxLayout()
        searchLayout.addWidget(searchLabel, 1, alignment=Qt.AlignRight)
        searchLayout.addSpacing(30)
        searchLayout.addWidget(self.searchBar, 0, alignment=Qt.AlignRight)

        layout = QVBoxLayout()
        layout.addLayout(searchLayout)
        layout.addWidget(self.tableView)
        self.setLayout(layout)

    def model(self) -> QAbstractItemModel:
        return self.tableView.model()

    def setModel(self, model: QAbstractItemModel) -> None:
        m: QAbstractItemModel = self.tableView.model()
        self.tableView.setModel(model)
        safeDelete(m)


class IndexTableModel(QAbstractTableModel):
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.__frameModel: FrameModel = None
        self.__checked: Set[int] = set()
        self.__indexList: List[Any] = list()

    @property
    def checked(self) -> List[Any]:
        """ Return the list of indexes value that are selected """
        return [self.__indexList[pos] for pos in self.__checked]

    def setFrameModel(self, frameModel: FrameModel) -> None:
        self.beginResetModel()
        if self.__frameModel:
            self.__frameModel.disconnect(self)

        # Reset internal fields
        self.__frameModel = frameModel
        self.__checked = set()
        self.__indexList = self.__frameModel.frame.getRawFrame().index.unique().to_list()

        # Connect to new frame model
        self.__frameModel.modelReset.connect(self.resetIndexList)
        self.endResetModel()

    @Slot()
    def resetIndexList(self) -> None:
        self.beginResetModel()
        self.__checked = set()
        self.__indexList = self.__frameModel.frame.getRawFrame().index.unique().to_list()
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid() or not self.__frameModel:
            return 0
        return len(self.__indexList)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return 2

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        if role == Qt.DisplayRole or role == Qt.EditRole:
            if index.column() == 0:
                return index.row() in self.__checked
            elif index.column() == 1:
                return str(self.__indexList[index.row()])
        return None

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.EditRole) -> bool:
        if index.column() == 0 and role == Qt.EditRole:
            if value:
                self.__checked.add(index.row())
            else:
                self.__checked.remove(index.row())
            self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
            return True
        return False

    def setAllChecked(self, value: bool) -> None:
        if value is True:
            self.__checked = set(n for n in range(self.rowCount()))
        else:
            self.__checked = set()
        sIndex = self.index(0, 0, QModelIndex())
        eIndex = self.index(self.rowCount() - 1, 0, QModelIndex())
        self.dataChanged.emit(sIndex, eIndex, [Qt.DisplayRole])

    @Slot(int)
    def onHeaderClicked(self, section: int) -> None:
        """ Slot to be called when user clicks on the table header """
        if section == 0:
            checked = self.headerData(section, Qt.Horizontal, Qt.DisplayRole)
            if checked is True:
                self.setAllChecked(False)
            else:
                self.setAllChecked(True)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section == 1:
                return 'Index'
            elif section == 0:
                return len(self.__checked) == self.rowCount()

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable | super().flags(index)
        if index.column() == 0:
            base |= Qt.ItemIsEditable
        return base


class IndexTableView(QTableView):
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setSelectionMode(QTableView.SingleSelection)
        self.setAlternatingRowColors(True)
        self.horizontalHeader().setSectionsClickable(True)
        self.verticalHeader().hide()

    def setModel(self, model: AttributeTableModel) -> None:
        """ Reimplemented to start fetch timer """
        super().setModel(model)
        self.setItemDelegateForColumn(0, BooleanBoxDelegate(self))
        self.horizontalHeader().resizeSection(0, 5)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)


# PANEL


class _SettingsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.timeAxisAttributeCB = QComboBox(self)
        self.valuesTable = SearchableAttributeTableWidget(self, True, False, True, [Types.Numeric,
                                                                                    Types.Ordinal])
        self.indexTable = SearchableTableWidget(self)
        self.meanCB = QCheckBox('Mean of selected', self)
        self.createButton = QPushButton('Create chart', self)

        sideLayout = QVBoxLayout(self)
        lab = QLabel('Select the column to use as time index')
        lab.setWordWrap(True)
        sideLayout.addWidget(lab)
        sideLayout.addWidget(self.timeAxisAttributeCB)

        lab = QLabel('Time axis format')
        self.timeAxisFormatCB = QComboBox(self)
        options = QStringListModel(['dd.MM.yyyy', 'yyyy-MM-dd', 'yyyy-MM', 'yyyy',
                                    'hh:mm:ss', 'hh:mm', 'hh', 'yyyy-MM-dd HH:mm:ss',
                                    'ddd MMM dd yyyy', 'ddd', 'MMM', 'dd', 'MMM yyyy'], parent=self)
        self.timeAxisFormatCB.setModel(options)
        self.timeAxisFormatCB.setCurrentIndex(0)
        sideLayout.addWidget(lab)
        sideLayout.addWidget(self.timeAxisFormatCB)

        lab = QLabel('Select any number of columns to show as a function of time')
        lab.setWordWrap(True)
        sideLayout.addSpacing(30)
        sideLayout.addWidget(lab)
        sideLayout.addWidget(self.valuesTable)

        lab = QLabel('Select the rows to show by index. An index attribute must be set')
        lab.setWordWrap(True)
        sideLayout.addSpacing(30)
        sideLayout.addWidget(lab)
        sideLayout.addWidget(self.indexTable)
        sideLayout.addWidget(self.meanCB)
        sideLayout.addSpacing(30)
        sideLayout.addWidget(self.createButton)

        self.errorLabel = QLabel(self)
        self.errorLabel.setWordWrap(True)
        sideLayout.addWidget(self.errorLabel)
        self.errorLabel.hide()


class TimeSeriesPlot(QWidget):
    def __init__(self, workbench: WorkbenchModel, parent: QWidget = None):
        super().__init__(parent)

        self.settingsPanel = _SettingsPanel(self)
        self.chartView = InteractiveChartView(parent=self, setInWindow=False)
        p: QSizePolicy = self.chartView.sizePolicy()
        p.setVerticalPolicy(QSizePolicy.Ignored)
        p.setHorizontalPolicy(QSizePolicy.Ignored)
        self.chartView.setSizePolicy(p)
        self.workbench = workbench
        self.searchableIndexTableModel: QSortFilterProxyModel = QSortFilterProxyModel(self)

        self.splitter = QSplitter(Qt.Horizontal, self)
        self.splitter.addWidget(self.chartView)
        self.splitter.addWidget(self.settingsPanel)
        layout = QHBoxLayout(self)
        layout.addWidget(self.splitter)

        self.settingsPanel.createButton.clicked.connect(self.createChart)
        self.settingsPanel.timeAxisFormatCB.currentTextChanged.connect(self.changeTimeFormat)

    @Slot(str)
    def changeTimeFormat(self, timeFormat: str) -> None:
        """ Changes the datetime format displayed on the X axis of the plot """
        chart = self.chartView.chart()
        if chart:
            axis = chart.axisX()
            if axis and axis.type() == QtCharts.QAbstractAxis.AxisTypeDateTime:
                axis.setFormat(timeFormat)
                self.chartView.setBestTickCount(chart.size())

    def __createTimeAxis(self, timeSeries: pd.Series, timeType: Type) -> QtCharts.QAbstractAxis:
        if timeType == Types.Datetime:
            # Time axis is Datetime
            xAxis = QtCharts.QDateTimeAxis()
            xAxis.setFormat(self.settingsPanel.timeAxisFormatCB.currentText())
        else:
            # Time axis is Ordinal (time are str labels)
            xAxis = QtCharts.QCategoryAxis()
            for cat, code in zip(timeSeries, timeSeries.cat.codes):
                xAxis.append(cat, code)
            xAxis.setStartValue(0)
            xAxis.setLabelsPosition(QtCharts.QCategoryAxis.AxisLabelsPositionOnValue)
        xAxis.setTitleText('Time')
        return xAxis

    @staticmethod
    def __createSeriesForAttributes(dataframe: pd.DataFrame, timeIndex: int, timeIndexType: Type):
        """ Creates a QLineSeries for every column in the dataframe. timeIndex column is used for
        xAxis """
        timeIndexName: str = dataframe.columns[timeIndex]

        # Convert time values to their numerical equivalent
        if timeIndexType == Types.Datetime:
            # Time axis is Datetime, so convert every date into the number of ms from 01/01/1970
            # dataframe[timeIndexName]: pd.Series[pd.Timestamp]
            dataframe.loc[:, timeIndexName] = dataframe[timeIndexName] \
                .map(lambda timestamp: int(timestamp.to_pydatetime().timestamp() * 1000))
        else:
            # Types.Ordinal
            # dataframe[timeIndexName]: pd.Series[pd.Categorical]
            dataframe.loc[:, timeIndexName] = dataframe[timeIndexName].cat.codes.to_list()

        timeValues: pd.Series = dataframe[timeIndexName]
        dataframe = dataframe.drop(timeIndexName, axis=1)

        # Create series for every column (excluding time)
        allSeries: List[QtCharts.QLineSeries] = list()
        for colName, valueSeries in dataframe.items():
            qSeries = QtCharts.QLineSeries()
            points = list(map(lambda t: QPointF(*t), zip(timeValues, valueSeries)))
            qSeries.append(points)
            qSeries.setName(colName)
            qSeries.setPointsVisible(True)
            qSeries.setUseOpenGL(True)
            allSeries.append(qSeries)
        return allSeries

    def __createChartWithValues(self, dataframe: pd.DataFrame, attributes: List[int], timeIndex: int,
                                timeIndexType: Type) -> QtCharts.QChart:
        chart = QtCharts.QChart()
        # Sort by time
        timeIndexName: str = dataframe.columns[timeIndex]
        filteredDf = dataframe.iloc[:, [timeIndex, *attributes]].sort_values(by=timeIndexName, axis=0,
                                                                             ascending=True)
        # filteredDf has timeIndex at position 0, attributes following

        # Create X axis
        timeSeries: pd.Series = filteredDf.iloc[:, 0]
        xAxis = self.__createTimeAxis(timeSeries, timeIndexType)
        chart.addAxis(xAxis, Qt.AlignBottom)

        # Create the Y axis
        yAxis = QtCharts.QValueAxis(chart)
        yAxis.setTitleText('Values')
        chart.addAxis(yAxis, Qt.AlignLeft)

        series = self.__createSeriesForAttributes(filteredDf, timeIndex=0, timeIndexType=timeIndexType)

        for s in series:
            chart.addSeries(s)
            s.attachAxis(xAxis)
            s.attachAxis(yAxis)
        return chart

    def __createChartWithIndexes(self, dataframe: pd.DataFrame, attributes: List[int],
                                 indexes: List[Any], timeIndex: int, timeIndexType: Type,
                                 indexMean: bool) -> QtCharts.QChart:
        timeIndexName: str = dataframe.columns[timeIndex]
        filteredDf = dataframe.loc[indexes, :].iloc[:, [timeIndex, *attributes]]
        filteredDf = filteredDf.sort_values(by=timeIndexName, axis=0, ascending=True)

        # Group rows by their index attribute. Every index has a distinct list of values
        dfByIndex = filteredDf.groupby(filteredDf.index)
        timeAxisColumn: pd.Series = list(dfByIndex)[0][1][timeIndexName]

        chart = QtCharts.QChart()
        # There will be 1 time axis for all the series, so it is created based on the first series
        # This function is passed the original time label (either Ordinal or Datetime)
        xAxis = self.__createTimeAxis(timeAxisColumn, timeIndexType)
        chart.addAxis(xAxis, Qt.AlignBottom)

        # Create the Y axis
        yAxis = QtCharts.QValueAxis(chart)
        yAxis.setTitleText('Values')
        # Add axis Y to chart
        chart.addAxis(yAxis, Qt.AlignLeft)

        # Add every index series
        groupedValues: pd.DataFrame  # timeValue, timeAttribute, *seriesValue
        for group, groupedValues in dfByIndex:
            # Create a series for this 'index'
            groupName: str = str(group)
            allSeries = self.__createSeriesForAttributes(groupedValues, 0, timeIndexType=timeIndexType)
            for series in allSeries:
                chart.addSeries(series)
                series.attachAxis(xAxis)
                series.attachAxis(yAxis)
            if len(allSeries) == 1:
                # Only 1 attribute was selected, so assume we have multiple indexes (groups)
                allSeries[0].setName(groupName)
        return chart

    @Slot()
    def createChart(self) -> None:
        # Get options
        timeAxis: str = self.settingsPanel.timeAxisAttributeCB.currentText()
        attributes: List[int] = self.settingsPanel.valuesTable.model().checked
        indexes: List[Any] = self.settingsPanel.indexTable.model().sourceModel().checked
        indexMean: bool = self.settingsPanel.meanCB.isChecked()

        # Possibilities:
        # 1) 0 indexes and 1+ attributes
        # 2) 1+ indexes and 1 attribute
        # 3) 1 index and 1+ attributes

        # Validation
        errors: str = ''
        if not timeAxis:
            errors += 'Error: no time axis is selected\n'
        if not attributes:
            errors += 'Error: at least one attribute to show must be selected\n'
        if len(attributes) > 1 and len(indexes) > 1:
            errors += 'Error: select either 0/1 index and 1 or more attributes or 1 attribute and 1 '
            'or more indexes\n'
        if errors:
            errors = errors.strip('\n')
            self.settingsPanel.errorLabel.setText(errors)
            self.settingsPanel.errorLabel.setStyleSheet('color: red')
            self.settingsPanel.errorLabel.show()
            return  # stop
        else:
            self.settingsPanel.errorLabel.hide()

        # Get the integer index of the time attribute
        timeIndexModel: QAbstractItemModel = self.settingsPanel.timeAxisAttributeCB.model()
        i = self.settingsPanel.timeAxisAttributeCB.currentIndex()
        timeIndex: int = timeIndexModel.mapToSource(timeIndexModel.index(i, 0, QModelIndex())).row()
        # Get the type of time attribute
        timeType: Type = self.settingsPanel.valuesTable.model().frameModel().shape.colTypes[timeIndex]
        # Get the pandas dataframe
        dataframe: pd.DataFrame = self.settingsPanel.valuesTable.model().frameModel().frame.getRawFrame()

        if len(attributes) >= 1 and len(indexes) == 0:
            # Create line plot with different attributes as series
            chart = self.__createChartWithValues(dataframe, attributes, timeIndex, timeType)
        elif (len(attributes) == 1 and len(indexes) >= 1) or \
                (len(attributes) >= 1 and len(indexes) == 1):
            # Create chart with 1 attribute and many indexes
            chart = self.__createChartWithIndexes(dataframe, attributes, indexes, timeIndex, timeType,
                                                  indexMean)
        else:
            raise NotImplementedError('Invalid chart parameters')

        chart.setDropShadowEnabled(False)
        chart.legend().setVisible(True)
        # Set font size for axis
        font: QFont = chart.axisX().labelsFont()
        font.setPointSize(9)
        chart.axisX().setLabelsFont(font)
        chart.axisY().setLabelsFont(font)
        chart.setMargins(QMargins(5, 5, 5, 30))
        chart.layout().setContentsMargins(2, 2, 2, 2)
        # Set new chart and delete previous one
        self.__setChart(chart)

    def __setChart(self, chart: QtCharts.QChart) -> None:
        oldChart = self.chartView.chart()
        self.chartView.setChart(chart)
        self.chartView.setBestTickCount(chart.size())
        safeDelete(oldChart)

    @Slot(int)
    def onFrameSelectionChanged(self, index: int) -> None:
        # Reset the ChartView
        self.clearChart()
        # Set attribute table
        frameModel = self.workbench.getDataframeModelByIndex(index)
        self.settingsPanel.valuesTable.setSourceFrameModel(frameModel)
        # Set up combo box for time axis
        timeAxisModel = AttributeTableModel(None, False, False, False)
        timeAxisModel.setFrameModel(frameModel)
        filteredModel = AttributeProxyModel(filterTypes=[Types.Datetime, Types.Ordinal], parent=self)
        filteredModel.setSourceModel(timeAxisModel)
        timeAxisModel.setParent(filteredModel)
        m = self.settingsPanel.timeAxisAttributeCB.model()
        self.settingsPanel.timeAxisAttributeCB.setModel(filteredModel)
        safeDelete(m)
        # Set up index table
        if self.searchableIndexTableModel.sourceModel():
            indexTableModel: IndexTableModel = self.searchableIndexTableModel.sourceModel()
            indexTableModel.setFrameModel(frameModel)
        else:
            # Searchable model has not a source model
            indexTableModel: IndexTableModel = IndexTableModel(self.searchableIndexTableModel)
            indexTableModel.setFrameModel(frameModel)
            # Set up proxy model
            self.searchableIndexTableModel.setSourceModel(indexTableModel)
            self.searchableIndexTableModel.setFilterKeyColumn(1)
            # Connect view to proxy model
            self.settingsPanel.indexTable.setModel(self.searchableIndexTableModel)
            self.settingsPanel.indexTable.searchBar.textEdited.connect(
                self.searchableIndexTableModel.setFilterRegularExpression)
            self.settingsPanel.indexTable.tableView.horizontalHeader().sectionClicked.connect(
                indexTableModel.onHeaderClicked)

    def clearChart(self) -> None:
        chart = self.chartView.chart()
        if chart:
            self.chartView.setChart(QtCharts.QChart())
            safeDelete(chart)

    def reset(self) -> None:
        m = self.settingsPanel.indexTable.model()
        if m:
            self.searchableIndexTableModel = QSortFilterProxyModel(self)
            self.settingsPanel.indexTable.setModel(self.searchableIndexTableModel)
            safeDelete(m)

        m = self.settingsPanel.timeAxisAttributeCB.model()
        if m:
            self.settingsPanel.timeAxisAttributeCB.setModel(QSortFilterProxyModel(self))
            safeDelete(m)

        self.clearChart()
