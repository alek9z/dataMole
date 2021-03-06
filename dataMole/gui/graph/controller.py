# -*- coding: utf-8 -*-
#
# Authors:      Alessandro Zangari (alessandro.zangari.code@outlook.com)
#               Nicolas Darques    (dsideb@gmail.com)
# Copyright:    © Copyright 2020 Alessandro Zangari, Università degli Studi di Padova
# License:      GPL-3.0-or-later
# Date:         2020-10-04
# Version:      1.0
#
# This file contains parts taken from "Nodegraph-pyqt" available at
# https://github.com/dsideb/nodegraph-pyqt
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

from typing import List, Callable, Dict, Set

from PySide2.QtCore import Slot
from PySide2.QtWidgets import QWidget, QMessageBox

from dataMole import flow, flogging, gui, exceptions as exp
from .node import NodeSlot, GraphNode, NodeStatus
from .scene import GraphScene
from .view import GraphView
from ..editor.configuration import configureEditor, configureEditorOptions
from ..workbench import WorkbenchModel
from ...flow.dag import OperationDag
from ...flow.handler import OperationHandler
from ...utils import safeDelete


class GraphController(QWidget):
    def __init__(self, operation_dag: flow.dag.OperationDag, scene: GraphScene, view: GraphView,
                 workbench_mod: WorkbenchModel, parent: QWidget = None):
        super().__init__(parent)
        self._scene: GraphScene = scene
        self._view: GraphView = view
        self._operation_dag: OperationDag = operation_dag
        self._workbench_model: WorkbenchModel = workbench_mod
        # Current active editor
        self.__editor_widget: gui.AbsOperationEditor = None
        # Current node being edited
        self.__editor_node_id: int = None
        # Flag to know when execution starts
        self.__executing = False
        # A reference to the handler must be kept while computation runs
        self.__handler = None
        # Connections
        self._scene.editModeEnabled.connect(self.startEditNode)
        self._view.deleteSelected.connect(self.removeItems)
        self._scene.createNewEdge.connect(self.addEdge)
        self._scene.dropNewNode.connect(self.addNode)

    @Slot(type)
    def addNode(self, op_class: Callable):
        if self.__executing:
            return
        op_input: bool = getattr(op_class, 'maxInputNumber')() == 0
        op_output: bool = getattr(op_class, 'minOutputNumber')() == 0
        if op_output or op_input:
            op = op_class(self._workbench_model)
        else:
            op = op_class()
        node = flow.dag.OperationNode(op)
        if self._operation_dag.addNode(node):
            inputs = ['in {}'.format(i) for i in range(op.maxInputNumber())]
            self._scene.create_node(name=op.name(), id=node.uid, optionsSet=op.hasOptions(),
                                    inputs=inputs, output=not op_output)

    @Slot(NodeSlot, NodeSlot)
    def addEdge(self, source_slot: NodeSlot, target_slot: NodeSlot):
        if self.__executing:
            return
        u: GraphNode = source_slot.parentNode
        v: GraphNode = target_slot.parentNode
        try:
            done = self._operation_dag.addConnection(source_id=u.id, target_id=v.id,
                                                     slot=target_slot.position)
        except exp.DagException as e:
            gui.notifier.addMessage(e.title if e.title else 'GraphEdge not added', e.message,
                                    QMessageBox.Critical)
        else:
            if done:
                self._scene.create_edge(source_slot, target_slot)

    @Slot()
    def removeItems(self):
        if self.__executing:
            return
        # We have to keep track of which nodes are updated, in order to update their options indicator
        nodesToUpdate: Set[int] = set()
        # Get selection
        selected_nodes: List[GraphNode] = self._scene.selectedNodes
        selected_edges: List['GraphEdge'] = self._scene.selectedEdges
        # Remove items one by one
        for edge in selected_edges:
            nodesToUpdate |= self._operation_dag.removeConnection(edge.sourceNode.id, edge.targetNode.id)
        for node in selected_nodes:
            nodesToUpdate |= self._operation_dag.removeNode(node.id)
        # Update the scene
        self._scene.delete_selected()
        # Update nodes that were not deleted (but whose edges changed)
        nodesToUpdate -= set(map(lambda n: n.id, selected_nodes))
        for nodeId in nodesToUpdate:
            op = self._operation_dag[nodeId].operation
            self._scene.updateNodeOptionIndicator(nodeId, op.hasOptions())

    @Slot(int)
    def startEditNode(self, node_id: int):
        flogging.appLogger.debug('Edit node slot')
        if self.__executing:
            flogging.appLogger.debug('Flow is executing, don\'t allow edit')
            return
        node: flow.dag.OperationNode = self._operation_dag[node_id]
        if not self.__editor_widget:
            flogging.appLogger.debug('Creating new editor')
            if not node.operation.needsOptions():
                msg_noeditor = QMessageBox()
                msg_noeditor.setWindowTitle(node.operation.name())
                msg_noeditor.setInformativeText(
                    '{:s}<hr>This operations require no options.'.format(
                        node.operation.shortDescription()))
                msg_noeditor.setStandardButtons(QMessageBox.Ok)
                msg_noeditor.exec_()
                msg_noeditor.deleteLater()
                return
            # Set up editor
            self.__editor_widget = node.operation.getEditor()
            self.__editor_node_id = node.uid
            # Create the central widget and adds options
            if node.operation.needsOptions():
                self.__editor_widget.setUpEditor()
            configureEditor(self.__editor_widget, node.operation, self._view)
            node.operation.injectEditor(self.__editor_widget)
            configureEditorOptions(self.__editor_widget, node.operation)
            # Connect editor signals to slots which handle accept/reject
            self.__editor_widget.accept.connect(self.onEditAccept)
            self.__editor_widget.reject.connect(self.cleanupEditor)
            # Show editor
            self.__editor_widget.move(self._view.rect().center())
            self.__editor_widget.show()
        else:
            flogging.appLogger.debug('Editor already opened {}'.format(type(self.__editor_widget)))
            # If an editor is currently opened show it, instead of creating a new one
            self.__editor_widget.activateWindow()
            self.__editor_widget.raise_()

    @Slot()
    def onEditAccept(self) -> None:
        options = self.__editor_widget.getOptions()
        try:
            if isinstance(options, dict):
                nodesUpdated = self._operation_dag.updateNodeOptions(self.__editor_node_id, **options)
            else:
                nodesUpdated = self._operation_dag.updateNodeOptions(self.__editor_node_id, *options)
        except exp.OperationError as e:
            if isinstance(e, exp.OptionValidationError):
                self.__editor_widget.handleErrors(e.invalid)
            else:
                # Signal generic error
                gui.notifier.addMessage(e.title, e.message, QMessageBox.Critical)
        else:
            # If validation succeed
            if nodesUpdated:
                # At least 1 node has been updated
                flogging.appLogger.debug('Graph node {} edited'.format(self.__editor_node_id))
                # Update the view for all the nodes that were updated
                for nodeId in nodesUpdated:
                    op = self._operation_dag[nodeId].operation
                    self._scene.updateNodeOptionIndicator(nodeId, op.hasOptions())
            else:
                # The view does not change if no node was updated
                gui.notifier.addMessage('Error occurred updating node',
                                        'Flow node {} was not updated'.format(self.__editor_node_id),
                                        icon=QMessageBox.Critical)
                flogging.appLogger.debug('Graph node {} was not updated'.format(self.__editor_node_id))
            # Delete editor
            self.cleanupEditor()

    @Slot()
    def cleanupEditor(self) -> None:
        # Do not call close() here, since this function is called after a closeEvent
        safeDelete(self.__editor_widget)
        self.__editor_node_id = None
        self.__editor_widget = None

    @Slot()
    def executeFlow(self) -> None:
        if self.__executing:
            gui.notifier.addMessage('Flow already in progress',
                                    'An operation is still executing. '
                                    'Starting more than one flow is not supported',
                                    QMessageBox.Warning)
            return
        # Reset status
        self.resetFlowStatus()
        self.__executing = True
        # Disable some features of view/scene
        self._view.setAcceptDrops(False)
        self._scene.disableEdit = True
        # Execute
        self.__handler = OperationHandler(self._operation_dag)
        self.__handler.signals.statusChanged.connect(self.onStatusChanged)
        self.__handler.signals.failedWithMessage.connect(self.onErrorException)
        self.__handler.signals.allFinished.connect(self.flowCompleted)
        try:
            gui.statusBar.startSpinner()
            gui.statusBar.showMessage('Started flow execution...', 20)
            self.__handler.execute()
        except exp.HandlerException as e:
            # These exceptions are thrown if the handler detects some errors before execution
            gui.statusBar.showMessage('Execution stopped', 20)
            gui.notifier.addMessage('Flow exception' if not e.title else e.title,
                                    e.message, QMessageBox.Critical)
            self.flowCompleted()

    @Slot()
    def resetFlowStatus(self) -> None:
        if self.__executing:
            return
        for node in self._scene.nodesDict.values():
            node.status = NodeStatus.NONE
            node.refresh(refresh_edges=False)
        flogging.appLogger.debug('Reset flow status')

    @Slot(int, NodeStatus)
    def onStatusChanged(self, uid: int, status: NodeStatus) -> None:
        node: GraphNode = self._scene.nodesDict[uid]
        flogging.appLogger.debug('GraphNode status changed in {} at node {} with id {}'
                                 .format(str(status), node.name, node.id))
        node.status = status
        node.refresh(refresh_edges=False)

    @Slot(int, str)
    def onErrorException(self, uid: int, msg: str) -> None:
        node: GraphNode = self._scene.nodesDict[uid]
        gui.notifier.addMessage(message=msg, title='"{}" failed'.format(node.name),
                                icon=QMessageBox.Critical)

    @Slot()
    def flowCompleted(self) -> None:
        gui.statusBar.showMessage('Flow finished', 20)
        gui.statusBar.stopSpinner()
        self.__executing = False
        self._view.setAcceptDrops(True)
        self._scene.disableEdit = False
        flogging.appLogger.debug('Flow finished controller slot called')

    def showGraphInScene(self) -> None:
        graph = self._operation_dag.getNxGraph()
        nodeDict = dict()

        def addNode(opNode, scene) -> GraphNode:
            op = opNode.operation
            inputNames = ['in {}'.format(i) for i in range(op.maxInputNumber())]
            isOutput: bool = op.minOutputNumber() == 0
            return scene.create_node(name=op.name(), id=opNode.uid, optionsSet=op.hasOptions(),
                                     inputs=inputNames, output=not isOutput)

        def addEdge(sourceItem, childItem, childNode, scene) -> None:
            inputs: Dict[int, int] = childNode.inputOrder
            sourceSlot: NodeSlot = sourceItem.slots[1][0]
            targetSlot: NodeSlot = childItem.slots[0][inputs[node_id]]
            scene.create_edge(sourceSlot, targetSlot)

        # Add all nodes
        for node_id in graph.nodes:
            nodeDict[node_id] = addNode(self._operation_dag[node_id], self._scene)

        # Add all edges
        for node_id in graph.nodes:
            parNode = nodeDict[node_id]
            for child_id in graph.successors(node_id):  # direct successors
                childNode: GraphNode = nodeDict[child_id]
                childOp = self._operation_dag[child_id]
                addEdge(parNode, childNode, childOp, self._scene)
