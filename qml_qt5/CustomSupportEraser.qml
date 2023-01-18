//-----------------------------------------------------------------------------
// Copyright (c) 2023 5@xes
// 
// proterties values
//   "SSize"        : Support Size in mm
//   "SBType"       : Support Blocker Type 
//   "OnBuildPlate" : Support Blocker reach Build plate
//   "SMsg"         : Text for the Remove All Button
//-----------------------------------------------------------------------------

import QtQuick 2.2
import QtQuick.Controls 1.2

import UM 1.1 as UM

Item
{
    id: base
    width: childrenRect.width
    height: childrenRect.height
    UM.I18nCatalog { id: catalog; name: "customsupporteraser"}

    property var s_size: UM.ActiveTool.properties.getValue("SSize")

    function setSBType(type)
    {
        // set checked state of mesh type buttons
		cubeButton.checked = type === 'cube'
		cylinderButton.checked = type === 'cylinder'
		customButton.checked = type === 'custom'
        UM.ActiveTool.setProperty("SBType", type)
    }
	
    Column
    {
        id: sTypeItems
        anchors.top: parent.top;
        anchors.left: parent.left;
        spacing: UM.Theme.getSize("default_margin").height;

        Row // Mesh type buttons
        {
            id: sTypeButtons
            spacing: UM.Theme.getSize("default_margin").width
			
            Button
            {
                id: cubeButton;
                text: catalog.i18nc("@label", "Cube")
                iconSource: "type_cube.svg"
                property bool needBorder: true
                checkable: true
                onClicked: setSBType('cube')
                style: UM.Theme.styles.tool_button
                checked: UM.ActiveTool.properties.getValue("SBType") === 'cube'
                z: 3; // Depth position 
            }

            Button
            {
                id: cylinderButton
                text: catalog.i18nc("@label", "Cylinder")
                iconSource: "type_cylinder.svg"
                property bool needBorder: true
                checkable:true
                onClicked: setSBType('cylinder')
                style: UM.Theme.styles.tool_button
                checked: UM.ActiveTool.properties.getValue("SBType") === 'cylinder'
                z: 2; // Depth position 
            }
			
            Button
            {
                id: customButton
                text: catalog.i18nc("@label", "Custom")
                iconSource: "type_custom.svg"
                property bool needBorder: true
                checkable:true
                onClicked: setSBType('custom')
                style: UM.Theme.styles.tool_button
                checked: UM.ActiveTool.properties.getValue("SBType") === 'custom'
                z: 1; // Depth position 
            }
        }
    }
    Grid
    {
        id: textfields;
        anchors.leftMargin: UM.Theme.getSize("default_margin").width
        anchors.top: sTypeItems.bottom
		anchors.topMargin: UM.Theme.getSize("default_margin").height

        columns: 2
        flow: Grid.TopToBottom
        spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

        Label
        {
            height: UM.Theme.getSize("setting_control").height
            text: catalog.i18nc("@label","Size")
            font: UM.Theme.getFont("default")
            color: UM.Theme.getColor("text")
            verticalAlignment: Text.AlignVCenter
            renderType: Text.NativeRendering
            width: Math.ceil(contentWidth) //Make sure that the grid cells have an integer width.
        }
 
        TextField
        {
            id: sizeTextField
            width: UM.Theme.getSize("setting_control").width
            height: UM.Theme.getSize("setting_control").height
            property string unit: "mm"
            style: UM.Theme.styles.text_field;
            text: UM.ActiveTool.properties.getValue("SSize")
            validator: DoubleValidator
            {
                decimals: 2
                bottom: 0.1
                locale: "en_US"
            }

            onEditingFinished:
            {
                var modified_text = text.replace(",", ".") // User convenience. We use dots for decimal values
                UM.ActiveTool.setProperty("SSize", modified_text)
            }
        }
    }
	
	Item
	{
		id: baseCheckBox
		width: childrenRect.width
		height: childrenRect.height
		anchors.leftMargin: UM.Theme.getSize("default_margin").width
		anchors.top: textfields.bottom
		anchors.topMargin: UM.Theme.getSize("default_margin").height
		
		CheckBox
		{
			id: useOnBuildPlateCheckbox
			anchors.top: baseCheckBox.top
			// anchors.topMargin: UM.Theme.getSize("default_margin").height
			anchors.left: parent.left
			text: catalog.i18nc("@option:check","Reach Build Plate")
			style: UM.Theme.styles.partially_checkbox

			checked: UM.ActiveTool.properties.getValue("OnBuildPlate")
			onClicked: UM.ActiveTool.setProperty("OnBuildPlate", checked)		
		}
	}
	
	Rectangle {
        id: rightRect
        anchors.top: baseCheckBox.bottom
		//color: UM.Theme.getColor("toolbar_background")
		color: "#00000000"
		width: UM.Theme.getSize("setting_control").width * 1.8
		height: UM.Theme.getSize("setting_control").height 
        anchors.left: parent.left
		anchors.topMargin: UM.Theme.getSize("default_margin").height
    }
	
	Button
	{
		id: removeAllButton
		anchors.centerIn: rightRect
		width: UM.Theme.getSize("setting_control").width
		height: UM.Theme.getSize("setting_control").height	
		text: catalog.i18nc("@label", UM.ActiveTool.properties.getValue("SMsg"))
		onClicked: UM.ActiveTool.triggerAction("removeAllSupportBlockerMesh")
	}
}
