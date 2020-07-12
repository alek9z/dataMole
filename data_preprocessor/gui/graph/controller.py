from typing import List, Callable

from PySide2.QtCore import Slot
from PySide2.QtWidgets import QWidget, QMessageBox

import data_preprocessor.flogging as flogging
import data_preprocessor.flow as flow
import data_preprocessor.gui as gui
from .node import NodeSlot, Node, NodeStatus
from .scene import GraphScene
from .view import GraphView
from ..workbench import WorkbenchModel
from ...flow.dag import OperationDag
from ...flow.handler import OperationHandler, HandlerException
from ...operation.interface.exceptions import OptionValidationError


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
            self._scene.create_node(name=op.name(), id=node.uid, inputs=inputs, output=not op_output)

    @Slot(NodeSlot, NodeSlot)
    def addEdge(self, source_slot: NodeSlot, target_slot: NodeSlot):
        if self.__executing:
            return
        u: Node = source_slot.parentNode
        v: Node = target_slot.parentNode
        if self._operation_dag.addConnection(source_id=u.id, target_id=v.id, slot=target_slot.position):
            self._scene.create_edge(source_slot, target_slot)

    @Slot()
    def removeItems(self):
        if self.__executing:
            return
        selected_nodes: List[Node] = self._scene.selectedNodes
        selected_edges: List['Edge'] = self._scene.selectedEdges
        for edge in selected_edges:
            self._operation_dag.removeConnection(edge.sourceNode.id, edge.targetNode.id)
        for node in selected_nodes:
            self._operation_dag.removeNode(node.id)
        # Update the scene
        self._scene.delete_selected()

    @Slot(int)
    def startEditNode(self, node_id: int):
        if self.__executing:
            return
        node: flow.dag.OperationNode = self._operation_dag[node_id]
        if not self.__editor_widget:
            if not node.operation.needsOptions():
                msg_noeditor = QMessageBox()
                msg_noeditor.setWindowTitle(node.operation.name())
                msg_noeditor.setInformativeText(
                    'This operations require no options.<hr><b>Operation description</b><br><br>' +
                    node.operation.shortDescription())
                msg_noeditor.setStandardButtons(QMessageBox.Ok)
                msg_noeditor.exec_()
                msg_noeditor.deleteLater()
                return
            # Set up editor
            self.__editor_widget = node.operation.getEditor()
            self.__editor_node_id = node.uid
            # Create the central widget and adds options
            self.__editor_widget.setUpEditor()
            node.operation.injectEditor(self.__editor_widget)
            self.__editor_widget.setDescription(node.operation.shortDescription(),
                                                node.operation.longDescription())
            options = node.operation.getOptions()
            if isinstance(options, dict):
                self.__editor_widget.setOptions(**options)
            else:
                self.__editor_widget.setOptions(*options)
            # Connect editor signals to slots which handle accept/reject
            self.__editor_widget.accept.connect(self.onEditAccept)
            self.__editor_widget.reject.connect(self.cleanupEditor)
            # Show the editor in new window
            self.__editor_widget.setParent(None)
            self.__editor_widget.setWindowTitle(node.operation.name())
            self.__editor_widget.move(self._view.rect().center())
            self.__editor_widget.show()
        else:
            self.__editor_widget.activateWindow()
            self.__editor_widget.raise_()

    @Slot()
    def onEditAccept(self) -> None:
        options = self.__editor_widget.getOptions()
        try:
            if isinstance(options, dict):
                graphUpdated = self._operation_dag.updateNodeOptions(self.__editor_node_id, **options)
            else:
                graphUpdated = self._operation_dag.updateNodeOptions(self.__editor_node_id, *options)
        except OptionValidationError as e:
            self.__editor_widget.handleErrors(e.invalid)
        else:
            # If validation succeed
            if graphUpdated:
                # TODO: Maybe update view
                flogging.appLogger.debug('Graph node {} edited'.format(self.__editor_node_id))
            else:
                # TODO: Maybe update view
                gui.notifier.addMessage('Error occurred updating node',
                                        'Flow node {} was not updated'.format(self.__editor_node_id),
                                        icon=QMessageBox.Critical)
                flogging.appLogger.debug('Graph node {} was not updated'.format(self.__editor_node_id))
                pass
            # Delete editor
            self.cleanupEditor()

    @Slot()
    def cleanupEditor(self) -> None:
        # Do not call close() here, since this function is called after a closeEvent
        self.__editor_widget.disconnect(self)
        self.__editor_widget.deleteLater()
        self.__editor_node_id = None
        self.__editor_widget = None

    @Slot()
    def executeFlow(self) -> None:
        if self.__executing:
            gui.notifier.addMessage('Flow already in progress',
                                    'An operation is still executing. '
                                    'Starting more than one flow is not supported',
                                    QMessageBox.Information)
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
        self.__handler.signals.allFinished.connect(self.flowCompleted)
        try:
            gui.statusBar.startSpinner()
            gui.statusBar.showMessage('Started flow execution...', 20)
            self.__handler.execute()
        except HandlerException as e:
            gui.statusBar.showMessage('Execution stopped', 20)
            gui.notifier.addMessage('Flow exception' if not e.title else e.title,
                                    str(e), QMessageBox.Information)
            self.flowCompleted()

    @Slot()
    def resetFlowStatus(self) -> None:
        if self.__executing:
            return
        for node in self._scene.nodes:
            node.status = NodeStatus.NONE
            node.refresh(refresh_edges=False)
        flogging.appLogger.debug('Reset flow status')

    @Slot(int, NodeStatus)
    def onStatusChanged(self, uid: int, status: NodeStatus):
        node: Node = next((n for n in self._scene.nodes if n.id == uid), None)
        flogging.appLogger.debug('Node status changed in {} at node {} with id {}'.format(str(status),
                                                                                          node.name,
                                                                                          node.id))
        node.status = status
        node.refresh(refresh_edges=False)

    @Slot()
    def flowCompleted(self) -> None:
        gui.statusBar.showMessage('Flow finished', 20)
        gui.statusBar.stopSpinner()
        self.__executing = False
        self._view.setAcceptDrops(True)
        self._scene.disableEdit = False
        flogging.appLogger.debug('Flow finished controller slot called')
