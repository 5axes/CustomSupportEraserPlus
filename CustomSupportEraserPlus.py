#--------------------------------------------------------------------------------------------
# Initial Copyright(c) 2018 Ultimaker B.V.
# Copyright (c) 2023 5axes
#--------------------------------------------------------------------------------------------
# Based on the SupportEraser plugin by Ultimaker B.V., and licensed under LGPLv3 or higher.
#
#  https://github.com/Ultimaker/Cura/tree/master/plugins/SupportEraser
#
#--------------------------------------------------------------------------------------------
# First release 01-17-2023  to change the initial plugin into Support Eraser
#
# V1.0.1 01-17-2023  Clean and Simplify plugin Code + Test Cura 4.X
# V1.0.2 01-18-2023  Introduce Translation
#
#--------------------------------------------------------------------------------------------

VERSION_QT5 = False
try:
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtWidgets import QApplication
except ImportError:
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtWidgets import QApplication
    VERSION_QT5 = True

from cura.CuraApplication import CuraApplication

from UM.Mesh.MeshData import MeshData, calculateNormalsFromIndexedVertices

from UM.Logger import Logger
from UM.Message import Message
from UM.Math.Matrix import Matrix
from UM.Math.Vector import Vector

from UM.Tool import Tool
from UM.Event import Event, MouseEvent
from UM.Mesh.MeshBuilder import MeshBuilder
from UM.Scene.Selection import Selection

from cura.PickingPass import PickingPass

from UM.Operations.GroupedOperation import GroupedOperation
from UM.Operations.AddSceneNodeOperation import AddSceneNodeOperation
from UM.Operations.RemoveSceneNodeOperation import RemoveSceneNodeOperation
from cura.Operations.SetParentOperation import SetParentOperation
from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator
# from UM.Scene.Selection import Selection

from UM.Settings.SettingInstance import SettingInstance

from cura.Scene.SliceableObjectDecorator import SliceableObjectDecorator
from cura.Scene.BuildPlateDecorator import BuildPlateDecorator
from cura.Scene.CuraSceneNode import CuraSceneNode

import math
import numpy
import os.path
import trimesh

from UM.Resources import Resources
from UM.i18n import i18nCatalog


Resources.addSearchPath(
    os.path.join(os.path.abspath(os.path.dirname(__file__)))
)  # Plugin translation file import

i18n_catalog = i18nCatalog("customsupporteraser")

if i18n_catalog.hasTranslationLoaded():
    Logger.log("i", "Custom Support Eraser Plus Plugin translation loaded!")
    

class CustomSupportEraserPlus(Tool):
    def __init__(self):
       
        super().__init__()
        
        self._all_picked_node = []
        
        self._Nb_Point = 0  
        
        # variable for menu dialog        
        self._UseSize = 5.0
        self._UseOnBuildPlate = False
        self._SBType = 'cube'
        self._SMsg = i18n_catalog.i18nc("@message", "Remove All") 
        
        # Shortcut
        if not VERSION_QT5:
            self._shortcut_key = Qt.Key.Key_B
        else:
            self._shortcut_key = Qt.Key_B
            
        self._controller = self.getController()

        self._Svg_Position = Vector
        self._selection_pass = None

        
        self._application = CuraApplication.getInstance()
        
        self.setExposedProperties("SSize" , "SBType" , "OnBuildPlate" , "SMsg")
        
        CuraApplication.getInstance().globalContainerStackChanged.connect(self._updateEnabled)
        
        # Note: if the selection is cleared with this tool active, there is no way to switch to
        # another tool than to reselect an object (by clicking it) because the tool buttons in the
        # toolbar will have been disabled. That is why we need to ignore the first press event
        # after the selection has been cleared.
        Selection.selectionChanged.connect(self._onSelectionChanged)
        self._had_selection = False
        self._skip_press = False

        self._had_selection_timer = QTimer()
        self._had_selection_timer.setInterval(0)
        self._had_selection_timer.setSingleShot(True)
        self._had_selection_timer.timeout.connect(self._selectionChangeDelay)
        
        # set the preferences to store the default value
        self._preferences = CuraApplication.getInstance().getPreferences()
        self._preferences.addPreference("CustomSupportEraserPlus/sb_type", "cube")
        self._preferences.addPreference("CustomSupportEraserPlus/s_size", 5)
        self._preferences.addPreference("CustomSupportEraserPlus/on_build_plate", False)
        
        # convert as string to avoid further issue
        self._SBType = str(self._preferences.getValue("CustomSupportEraserPlus/sb_type"))
        # convert as float to avoid further issue
        self._UseSize = float(self._preferences.getValue("CustomSupportEraserPlus/s_size"))
        # convert as boolean to avoid further issue
        self._UseOnBuildPlate = bool(self._preferences.getValue("CustomSupportEraserPlus/on_build_plate"))
                
    def event(self, event):
        super().event(event)
        modifiers = QApplication.keyboardModifiers()
        if not VERSION_QT5:
            ctrl_is_active = modifiers & Qt.KeyboardModifier.ControlModifier
            shift_is_active = modifiers & Qt.KeyboardModifier.ShiftModifier
            alt_is_active = modifiers & Qt.KeyboardModifier.AltModifier
        else:
            ctrl_is_active = modifiers & Qt.ControlModifier
            shift_is_active = modifiers & Qt.ShiftModifier
            alt_is_active = modifiers & Qt.AltModifier

        
        if event.type == Event.MousePressEvent and MouseEvent.LeftButton in event.buttons and self._controller.getToolsEnabled():
            if ctrl_is_active:
                self._controller.setActiveTool("TranslateTool")
                return
                
            if self._skip_press:
                # The selection was previously cleared, do not add/remove an support mesh but
                # use this click for selection and reactivating this tool only.
                self._skip_press = False
                return

            if self._selection_pass is None:
                # The selection renderpass is used to identify objects in the current view
                self._selection_pass = CuraApplication.getInstance().getRenderer().getRenderPass("selection")
                
            picked_node = self._controller.getScene().findObject(self._selection_pass.getIdAtPosition(event.x, event.y))
            
            
            if not picked_node:
                # There is no slicable object at the picked location
                return

            node_stack = picked_node.callDecoration("getStack")
            if node_stack:
                if node_stack.getProperty("anti_overhang_mesh", "value") and not alt_is_active:
                    self._removeSupportBlockerMesh(picked_node)
                    return

                elif node_stack.getProperty("support_mesh", "value") or node_stack.getProperty("anti_overhang_mesh", "value") or node_stack.getProperty("infill_mesh", "value") or node_stack.getProperty("cutting_mesh", "value"):
                    # Only "normal" meshes can have anti_overhang_mesh added to them
                    return

            # Create a pass for picking a world-space location from the mouse location
            active_camera = self._controller.getScene().getActiveCamera()
            picking_pass = PickingPass(active_camera.getViewportWidth(), active_camera.getViewportHeight())
            picking_pass.render()
            
            # Type Custom need to select Two points
            if self._SBType == 'custom': 
                self._Nb_Point += 1
                if self._Nb_Point == 2 :
                    picked_position =  self._Svg_Position 
                    picked_position_b = picking_pass.getPickedPosition(event.x, event.y)
                    self._Svg_Position = picked_position_b
                    self._Nb_Point = 0
                    # Add the anti_overhang_mesh cube at the picked location
                    self._createSupportEraserMesh(picked_node, picked_position,picked_position_b)
                else:
                    self._Svg_Position = picking_pass.getPickedPosition(event.x, event.y)
            
            else:
                self._Nb_Point = 0
                picked_position =  picking_pass.getPickedPosition(event.x, event.y)
                picked_position_b = picking_pass.getPickedPosition(event.x, event.y)
                self._Svg_Position = picked_position_b
                    
                # Add the anti_overhang_mesh cube at the picked location
                self._createSupportEraserMesh(picked_node, picked_position,picked_position_b)


    def _createSupportEraserMesh(self, parent: CuraSceneNode, position: Vector , position2: Vector):
        node = CuraSceneNode()
    
        if self._SBType == 'cube':
            node.setName("EraserCube")
        elif self._SBType == 'cylinder':
            node.setName("EraserCylinder")           
        else:
            node.setName("EraserCustom")
            
        node.setSelectable(True)
        
        # long=Support Height
        if self._UseOnBuildPlate :
            self._long=position.y
        else :
            # Change de Height for the Cylinder to the radius
            if self._SBType == 'cylinder':
                self._long=self._UseSize*0.5
            else :
                self._long=self._UseSize
        
        if self._long >= position.y :
            self._long=position.y
            
        # Logger.log("d", "Long Support= %s", str(self._long))
        
        # For Cube/Cylinder
        # Test with 0.05 because the precision on the clic poisition is not very thight 
        if self._SBType == 'cube' :
            self._Sup = self._UseSize*0.05
        else :
            self._Sup = self._UseSize*0.01
                
        # Logger.log("d", "Additional Long Support = %s", str(self._long+self._Sup))    
            
        if self._SBType == 'cube':
            # Cube creation Size , length , top Additional Height
            mesh =  self._createCube(self._UseSize,self._long,self._Sup)
        elif self._SBType == 'cylinder':
            # Cylinder creation Diameter , Increment angle 10°, length , top Additional Height
            mesh = self._createCylinder(self._UseSize,10,self._long,self._Sup)            
        else:           
            # Custom creation Size , P1 as vector P2 as vector           
            mesh =  self._createCustom(self._UseSize,position,position2,self._Sup)

        node.setMeshData(mesh.build())

        # test for init position
        node_transform = Matrix()
        node_transform.setToIdentity()
        node.setTransformation(node_transform)
        
        active_build_plate = CuraApplication.getInstance().getMultiBuildPlateModel().activeBuildPlate
        node.addDecorator(BuildPlateDecorator(active_build_plate))
        node.addDecorator(SliceableObjectDecorator())
              
        stack = node.callDecoration("getStack") # created by SettingOverrideDecorator that is automatically added to CuraSceneNode

        settings = stack.getTop()

        # Define the new mesh as "anti_overhang_mesh" 
        definition = stack.getSettingDefinition("anti_overhang_mesh")
        new_instance = SettingInstance(definition, settings)
        new_instance.setProperty("value", True)
        new_instance.resetState()  # Ensure that the state is not seen as a user state.
        settings.addInstance(new_instance)
            
        op = GroupedOperation()
        # First add node to the scene at the correct position/scale, before parenting, so the support mesh does not get scaled with the parent
        op.addOperation(AddSceneNodeOperation(node, self._controller.getScene().getRoot()))
        op.addOperation(SetParentOperation(node, parent))
        op.push()
        node.setPosition(position, CuraSceneNode.TransformSpace.World)
        self._all_picked_node.append(node)
        self._SMsg = i18n_catalog.i18nc("@message", "Remove Last") 
        self.propertyChanged.emit()
        
        CuraApplication.getInstance().getController().getScene().sceneChanged.emit(node)

    def _removeSupportBlockerMesh(self, node: CuraSceneNode):
        parent = node.getParent()
        if parent == self._controller.getScene().getRoot():
            parent = None

        op = RemoveSceneNodeOperation(node)
        op.push()

        if parent and not Selection.isSelected(parent):
            Selection.add(parent)

        CuraApplication.getInstance().getController().getScene().sceneChanged.emit(node)

    def _updateEnabled(self):
        plugin_enabled = False

        global_container_stack = CuraApplication.getInstance().getGlobalContainerStack()
        if global_container_stack:
            plugin_enabled = global_container_stack.getProperty("anti_overhang_mesh", "enabled")

        CuraApplication.getInstance().getController().toolEnabledChanged.emit(self._plugin_id, plugin_enabled)
    
    def _onSelectionChanged(self):
        # When selection is passed from one object to another object, first the selection is cleared
        # and then it is set to the new object. We are only interested in the change from no selection
        # to a selection or vice-versa, not in a change from one object to another. A timer is used to
        # "merge" a possible clear/select action in a single frame
        if Selection.hasSelection() != self._had_selection:
            self._had_selection_timer.start()

    def _selectionChangeDelay(self):
        has_selection = Selection.hasSelection()
        if not has_selection and self._had_selection:
            self._skip_press = True
        else:
            self._skip_press = False

        self._had_selection = has_selection
        
    # Cube Support Blocker Creation
    def _createCube(self, size, height, sup ):
        mesh = MeshBuilder()

        # Intial Comment from Ultimaker B.V. I have never try to verify this point
        # Can't use MeshBuilder.addCube() because that does not get per-vertex normals
        # Per-vertex normals require duplication of vertices
        s = size / 2
        l = height 
        s_inf=s
        
        nbv=24        
        verts = [ # 6 faces with 4 corners each
            [-s_inf, -l,  s_inf], [-s,  sup,  s], [ s,  sup,  s], [ s_inf, -l,  s_inf],
            [-s,  sup, -s], [-s_inf, -l, -s_inf], [ s_inf, -l, -s_inf], [ s,  sup, -s],
            [ s_inf, -l, -s_inf], [-s_inf, -l, -s_inf], [-s_inf, -l,  s_inf], [ s_inf, -l,  s_inf],
            [-s,  sup, -s], [ s,  sup, -s], [ s,  sup,  s], [-s,  sup,  s],
            [-s_inf, -l,  s_inf], [-s_inf, -l, -s_inf], [-s,  sup, -s], [-s,  sup,  s],
            [ s_inf, -l, -s_inf], [ s_inf, -l,  s_inf], [ s,  sup,  s], [ s,  sup, -s]
        ]
        mesh.setVertices(numpy.asarray(verts, dtype=numpy.float32))

        indices = []
        for i in range(0, nbv, 4): # All 6 quads (12 triangles)
            indices.append([i, i+2, i+1])
            indices.append([i, i+3, i+2])
        mesh.setIndices(numpy.asarray(indices, dtype=numpy.int32))

        mesh.calculateNormals()
        return mesh      
        
    # Cylinder Support Blocker Creation
    def _createCylinder(self, size, nb , height , sup ):
        mesh = MeshBuilder()
        # Per-vertex normals require duplication of vertices
        r = size / 2

        l = -height
        rng = int(360 / nb)
        ang = math.radians(nb)
        r_inf=r
        
        verts = []

        nbv=12
        for i in range(0, rng):
            # Top
            verts.append([0, sup, 0])
            verts.append([r*math.cos((i+1)*ang), sup, r*math.sin((i+1)*ang)])
            verts.append([r*math.cos(i*ang), sup, r*math.sin(i*ang)])
            #Side 1a
            verts.append([r*math.cos(i*ang), sup, r*math.sin(i*ang)])
            verts.append([r*math.cos((i+1)*ang), sup, r*math.sin((i+1)*ang)])
            verts.append([r_inf*math.cos((i+1)*ang), l, r_inf*math.sin((i+1)*ang)])
            #Side 1b
            verts.append([r_inf*math.cos((i+1)*ang), l, r_inf*math.sin((i+1)*ang)])
            verts.append([r_inf*math.cos(i*ang), l, r_inf*math.sin(i*ang)])
            verts.append([r*math.cos(i*ang), sup, r*math.sin(i*ang)])
            #Bottom 
            verts.append([0, l, 0])
            verts.append([r_inf*math.cos(i*ang), l, r_inf*math.sin(i*ang)])
            verts.append([r_inf*math.cos((i+1)*ang), l, r_inf*math.sin((i+1)*ang)])
        
        mesh.setVertices(numpy.asarray(verts, dtype=numpy.float32))

        indices = []
        # for every angle increment nbv (12 or 18) Vertices
        tot = rng * nbv
        for i in range(0, tot, 3): # 
            indices.append([i, i+1, i+2])
        mesh.setIndices(numpy.asarray(indices, dtype=numpy.int32))

        mesh.calculateNormals()
        return mesh
        
    # Custom Support Blocker Creation
    def _createCustom(self, size, pos1 , pos2, sup):
        mesh = MeshBuilder()
        # Init point
        Pt1 = Vector(pos1.x,pos1.z,pos1.y)
        Pt2 = Vector(pos2.x,pos2.z,pos2.y)

        V_Dir = Pt2 - Pt1

        # Calcul vecteur
        s = size / 2

        l_a = pos1.y 
        l_b = pos2.y 
 
        Vtop = Vector(0,0,sup)
        VZ = Vector(0,0,s)
        VZa = Vector(0,0,-l_a)
        VZb = Vector(0,0,-l_b)
        
        Norm=Vector.cross(V_Dir,VZ).normalized()
        Dec = Vector(Norm.x*s,Norm.y*s,Norm.z*s)
            
        nbv=24

        # X Z Y
        # t=Top
        P_1t = Vtop+Dec
        P_2t = Vtop-Dec
        P_3t = V_Dir+Vtop+Dec
        P_4t = V_Dir+Vtop-Dec
        # i=Inf
        P_1i = VZa+Dec
        P_2i = VZa-Dec
        P_3i = VZb+V_Dir+Dec
        P_4i = VZb+V_Dir-Dec
         
        """
        1) Top
        2) Front
        3) Left
        4) Right
        5) Back 
        6) Bottom
        """
        verts = [ # 6 faces with 4 corners each
            [P_1t.x, P_1t.z, P_1t.y], [P_2t.x, P_2t.z, P_2t.y], [P_4t.x, P_4t.z, P_4t.y], [P_3t.x, P_3t.z, P_3t.y],
            [P_1t.x, P_1t.z, P_1t.y], [P_3t.x, P_3t.z, P_3t.y], [P_3i.x, P_3i.z, P_3i.y], [P_1i.x, P_1i.z, P_1i.y],
            [P_2t.x, P_2t.z, P_2t.y], [P_1t.x, P_1t.z, P_1t.y], [P_1i.x, P_1i.z, P_1i.y], [P_2i.x, P_2i.z, P_2i.y],
            [P_3t.x, P_3t.z, P_3t.y], [P_4t.x, P_4t.z, P_4t.y], [P_4i.x, P_4i.z, P_4i.y], [P_3i.x, P_3i.z, P_3i.y],
            [P_4t.x, P_4t.z, P_4t.y], [P_2t.x, P_2t.z, P_2t.y], [P_2i.x, P_2i.z, P_2i.y], [P_4i.x, P_4i.z, P_4i.y],
            [P_1i.x, P_1i.z, P_1i.y], [P_2i.x, P_2i.z, P_2i.y], [P_4i.x, P_4i.z, P_4i.y], [P_3i.x, P_3i.z, P_3i.y]
        ]
        
        mesh.setVertices(numpy.asarray(verts, dtype=numpy.float32))

        indices = []
        for i in range(0, nbv, 4): # All 6 quads (12 triangles)
            indices.append([i, i+2, i+1])
            indices.append([i, i+3, i+2])
        mesh.setIndices(numpy.asarray(indices, dtype=numpy.int32))

        mesh.calculateNormals()
        return mesh

    def removeAllSupportBlockerMesh(self):
        if self._all_picked_node:
            for node in self._all_picked_node:
                node_stack = node.callDecoration("getStack")
                if node_stack.getProperty("anti_overhang_mesh", "value"):
                    self._removeSupportBlockerMesh(node)
            self._all_picked_node = []
            self._SMsg = i18n_catalog.i18nc("@message", "Remove All") 
            self.propertyChanged.emit()
        else:        
            for node in DepthFirstIterator(self._application.getController().getScene().getRoot()):
                if node.callDecoration("isSliceable"):
                    # N_Name=node.getName()
                    # Logger.log('d', 'isSliceable : ' + str(N_Name))
                    node_stack=node.callDecoration("getStack")           
                    if node_stack:        
                        if node_stack.getProperty("anti_overhang_mesh", "value"):
                            # N_Name=node.getName()
                            # Logger.log('d', 'SupportBlockerMesh : ' + str(N_Name)) 
                            self._removeSupportBlockerMesh(node)
        
    def getSSize(self) -> float:
        """ 
            return: global _UseSize  in mm.
        """           
        return self._UseSize
  
    def setSSize(self, SSize: str) -> None:
        """
        param SSize: Size in mm.
        """
 
        try:
            s_value = float(SSize)
        except ValueError:
            return

        if s_value <= 0:
            return
        
        #Logger.log('d', 's_value : ' + str(s_value))        
        self._UseSize = s_value
        self._preferences.setValue("CustomSupportEraserPlus/s_size", s_value)       
       
    def getSMsg(self) -> bool:
        """ 
            return: global _SMsg  as text paramater.
        """ 
        return self._SMsg
    
    def setSMsg(self, SMsg: str) -> None:
        """
        param SMsg: SMsg as text paramater.
        """
        self._SMsg = SMsg
        
    def getSBType(self) -> bool:
        """ 
            return: global _SBType  as text paramater.
        """ 
        return self._SBType
    
    def setSBType(self, SBType: str) -> None:
        """
        param SBType: SBType as text paramater.
        """
        self._SBType = SBType
        # Logger.log('d', 'SBType : ' + str(SBType))   
        self._preferences.setValue("CustomSupportEraserPlus/sb_type", SBType)
        
    def getOnBuildPlate(self) -> bool:
        """ 
            return: global _UseOnBuildPlate  as boolean.
        """ 
        return self._UseOnBuildPlate
    
    def setOnBuildPlate(self, OnBuildPlate: bool) -> None:
        """
        param OnBuildPlate: as boolean.
        """
        self._UseOnBuildPlate = OnBuildPlate
        self._preferences.setValue("CustomSupportEraserPlus/on_build_plate", OnBuildPlate)
 
