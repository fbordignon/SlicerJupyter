import ctk, qt, slicer, vtk

def displayable(obj):
  """Convert Slicer-specific objects to displayable objects.
  Currently, it supports vtkMRMLMarkupsNode, vtkMRMLTableNode, vtkMRMLModelNode, vtkMRMLTransformNode.
  """
  try:

    # Workaround until xeus-python support matplotlib inline backend
    if str(type(obj)) == "<class 'matplotlib.figure.Figure'>":
      return MatplotlibDisplay(obj)

    if hasattr(obj, "IsA"):
      # MRML node
      if obj.IsA("vtkMRMLMarkupsNode"):
        return slicer.util.dataframeFromMarkups(obj)
      elif obj.IsA("vtkMRMLTableNode"):
        return slicer.util.dataframeFromTable(obj)
      elif obj.IsA("vtkMRMLModelNode"):
        return ModelDisplay(obj)
      elif obj.IsA("vtkMRMLTransformNode"):
        return TransformDisplay(obj)

  except:
    # Error occurred, most likely the input was not a known object type
    return obj

  # Unknown object
  return obj

class ModelDisplay(object):
  """This class displays a model node in a Jupyter notebook cell by rendering it as an image.
    :param modelNode: model node to display.
    :param imageSize: list containing width and height of the generated image, in pixels (default is `[300, 300]`).
    :param zoom: allows zooming in on the rendered model (default: 1.0).
    :param orientation: roll, pitch, yaw rotation angles of the camera, in degrees.
    :param showFeatureEdges: outline sharp edges with lines to improve visibility.
  """

  def __init__(self, modelNode, imageSize=None, orientation=None, zoom=None, showFeatureEdges=False):
    # rollPitchYawDeg
    orientation = [0,0,0] if orientation is None else orientation
    zoom = 1.0 if zoom is None else zoom
    imageSize = [300,300] if imageSize is None else imageSize
    showFeatureEdges = showFeatureEdges

    modelPolyData = modelNode.GetPolyData()

    renderer = vtk.vtkRenderer()
    renderer.SetBackground(1,1,1)
    renderer.SetUseDepthPeeling(1)
    renderer.SetMaximumNumberOfPeels(100)
    renderer.SetOcclusionRatio(0.1)
    renWin = vtk.vtkRenderWindow()
    renWin.OffScreenRenderingOn()
    renWin.SetSize(imageSize[0], imageSize[1])
    renWin.SetAlphaBitPlanes(1)  # for depth peeling
    renWin.SetMultiSamples(0)  # for depth peeling
    renWin.AddRenderer(renderer)

    renderer.GetActiveCamera()  # create active camera

    # Must be called after iren and renderer are linked and camera is created or there will be problems
    renderer.Render()

    modelNormals = vtk.vtkPolyDataNormals()
    modelNormals.SetInputData(modelPolyData)

    modelMapper = vtk.vtkPolyDataMapper()
    modelMapper.SetInputConnection(modelNormals.GetOutputPort())

    modelActor = vtk.vtkActor()
    modelActor.SetMapper(modelMapper)
    modelActor.GetProperty().SetColor(0.9, 0.9, 0.9)
    modelActor.GetProperty().SetOpacity(0.8)
    renderer.AddActor(modelActor)

    triangleFilter = vtk.vtkTriangleFilter()
    triangleFilter.SetInputConnection(modelNormals.GetOutputPort())

    if showFeatureEdges:

      edgeExtractor = vtk.vtkFeatureEdges()
      edgeExtractor.SetInputConnection(triangleFilter.GetOutputPort())
      edgeExtractor.ColoringOff()
      edgeExtractor.BoundaryEdgesOn()
      edgeExtractor.ManifoldEdgesOn()
      edgeExtractor.NonManifoldEdgesOn()

      modelEdgesMapper = vtk.vtkPolyDataMapper()
      modelEdgesMapper.SetInputConnection(edgeExtractor.GetOutputPort())
      modelEdgesMapper.SetResolveCoincidentTopologyToPolygonOffset()
      modelEdgesActor = vtk.vtkActor()
      modelEdgesActor.SetMapper(modelEdgesMapper)
      modelEdgesActor.GetProperty().SetColor(0.0, 0.0, 0.0)
      renderer.AddActor(modelEdgesActor)

    # Set projection to parallel to enable estimate distances
    renderer.GetActiveCamera().ParallelProjectionOn()
    renderer.GetActiveCamera().Roll(orientation[0])
    renderer.GetActiveCamera().Pitch(orientation[1])
    renderer.GetActiveCamera().Yaw(orientation[2])
    renderer.ResetCamera()
    renderer.GetActiveCamera().Zoom(zoom)

    windowToImageFilter = vtk.vtkWindowToImageFilter()
    windowToImageFilter.SetInput(renWin)
    windowToImageFilter.Update()

    screenshot = ctk.ctkVTKWidgetsUtils.vtkImageDataToQImage(windowToImageFilter.GetOutput())

    bArray = qt.QByteArray()
    buffer = qt.QBuffer(bArray)
    buffer.open(qt.QIODevice.WriteOnly)
    screenshot.save(buffer, "PNG")
    self.dataValue = bArray.toBase64().data().decode()
    self.dataType = "image/png"

  def _repr_mimebundle_(self, include=None, exclude=None):
    return { self.dataType: self.dataValue }

class TransformDisplay(object):
  """This class displays information about a transform in a Jupyter notebook cell.
  """
  def __init__(self, transform):
    if transform.IsLinear():
      # Always print linear transforms as transform to parent matrix
      self.dataValue = "Transform to parent:<br><pre>"+np.array2string(slicer.util.arrayFromTransformMatrix(transform))+"</pre>"
    else:
      # Non-linear transform
      if transform.GetTransformToParentAs('vtkAbstractTransform', False, True):
        # toParent is set (fromParent is just computed)
        self.dataValue = 'Transform to parent:<br>'
        self.dataValue += transform.GetTransformToParentInfo().replace('\n','<br>')
      else:
        # fromParent is set (toParent is just computed)
        self.dataValue = 'Transform from parent:<br>'
        self.dataValue += transform.GetTransformFromParentInfo().replace('\n','<br>')
  def _repr_mimebundle_(self, include=None, exclude=None):
    return { "text/html": self.dataValue }


class ViewDisplay(object):
  """This class captures current views and makes it available
  for display in the output of a Jupyter notebook cell.
  :param viewLayout: view layout name, most common ones are
    `FourUp`, `Conventional`, `OneUp3D`, `OneUpRedSlice`, `OneUpYellowSlice`,
    `OneUpPlot`, `OneUpGreenSlice`, `Dual3D`, `FourOverFour`, `DicomBrowser`.
    See :py:meth:`setViewLayout` for more details on viewLayout names.
  :param center: re-center slice and 3D views on current view content.
  """
  def __init__(self, viewLayout=None, center=True):
    layoutManager = slicer.app.layoutManager()
    if viewLayout:
      setViewLayout(viewLayout)
    if center:
      slicer.util.resetSliceViews()
      for viewId in range(layoutManager.threeDViewCount):
        reset3DView(viewId)
    slicer.util.setViewControllersVisible(False)
    slicer.app.processEvents()
    slicer.util.forceRenderAllViews()
    screenshot = layoutManager.viewport().grab()
    slicer.util.setViewControllersVisible(True)
    bArray = qt.QByteArray()
    buffer = qt.QBuffer(bArray)
    buffer.open(qt.QIODevice.WriteOnly)
    screenshot.save(buffer, "PNG")
    self.dataValue = bArray.toBase64().data().decode()
    self.dataType = "image/png"
  def _repr_mimebundle_(self, include=None, exclude=None):
    return { self.dataType: self.dataValue }

class ViewSliceDisplay(object):
  """This class captures a slice view and makes it available
  for display in the output of a Jupyter notebook cell.
  :param viewName: name of the slice view, such as `Red`, `Green`, `Yellow`.
    Get list of all current slice view names by calling `slicer.app.layoutManager().sliceViewNames()`.
  """
  def __init__(self, viewName=None, positionPercent=None):
    if not viewName:
      viewName = "Red"
    layoutManager = slicer.app.layoutManager()
    slicer.app.processEvents()
    sliceWidget = layoutManager.sliceWidget(viewName)
    if positionPercent is not None:
      sliceBounds = [0,0,0,0,0,0]
      sliceWidget.sliceLogic().GetLowestVolumeSliceBounds(sliceBounds)
      positionMin = sliceBounds[4]
      positionMax = sliceBounds[5]
      position = positionMin + positionPercent / 100.0 * (positionMax - positionMin)
      sliceWidget.sliceController().sliceOffsetSlider().setValue(position)
    sliceView = sliceWidget.sliceView()
    sliceView.forceRender()
    screenshot = sliceView.grab()
    bArray = qt.QByteArray()
    buffer = qt.QBuffer(bArray)
    buffer.open(qt.QIODevice.WriteOnly)
    #screenshot.save(buffer, "PNG")
    screenshot.save(buffer, "JPG")
    self.dataValue = bArray.toBase64().data().decode()
    #self.dataType = "image/png"
    self.dataType = "image/jpeg"
  def _repr_mimebundle_(self, include=None, exclude=None):
    return { self.dataType: self.dataValue }

class View3DDisplay(object):
  """This class captures a 3D view and makes it available
  for display in the output of a Jupyter notebook cell.
  :param viewID: integer index of the 3D view node. Valid values are between 0 and `slicer.app.layoutManager().threeDViewCount-1`.
  :param orientation: rotation angles of the camera around R, A, S axes, in degrees.
  """
  def __init__(self, viewID=0, orientation=None):
    slicer.app.processEvents()
    widget = slicer.app.layoutManager().threeDWidget(viewID)
    view = widget.threeDView()
    if orientation is not None:
      camera = view.interactorStyle().GetCameraNode().GetCamera()
      cameraToWorld = vtk.vtkTransform()
      cameraToWorld.RotateX(90)
      cameraToWorld.RotateY(180)
      cameraToWorld.RotateY(orientation[2])
      cameraToWorld.RotateX(orientation[1])
      cameraToWorld.RotateZ(orientation[0])
      cameraToWorld.Translate(0, 0, camera.GetDistance())
      viewUp = [0,1,0,0]
      slicer.vtkAddonMathUtilities.GetOrientationMatrixColumn(cameraToWorld.GetMatrix(), 1, viewUp)
      position = cameraToWorld.GetPosition()
      focalPoint = camera.GetFocalPoint()
      camera.SetPosition(focalPoint[0]+position[0], focalPoint[1]+position[1], focalPoint[2]+position[2])
      camera.SetViewUp(viewUp[0:3])
      camera.OrthogonalizeViewUp()
    view.forceRender()
    screenshot = view.grab()
    bArray = qt.QByteArray()
    buffer = qt.QBuffer(bArray)
    buffer.open(qt.QIODevice.WriteOnly)
    #screenshot.save(buffer, "PNG")
    screenshot.save(buffer, "JPG")
    self.dataValue = bArray.toBase64().data().decode()
    #dataType = "image/png"
    self.dataType = "image/jpeg"
  def _repr_mimebundle_(self, include=None, exclude=None):
    return { self.dataType: self.dataValue }


class ViewLightboxDisplay(object):
  """This class returns an image containing content of a slice view as it is sweeped over the displayed volume
  as an object to be displayed in a Jupyter notebook cell.
  :param viewName: :param viewName: name of the slice view, such as `Red`, `Green`, `Yellow`.
    Get list of all current slice view names by calling `slicer.app.layoutManager().sliceViewNames()`.
  :param rows: number of image rows.
  :param columns: number of image columns.
  :param positionRange: list of two float values, specifying start and end distance from the origin
    along the slice normal.
  :param rangeShrink: list of two float values, which modify the position range (positive value shrinks the range, on both sides).
    Useful for cropping irrelevant regions near the image boundaries.
  """

  def __init__(self, viewName=None, rows=None, columns=None, filename=None, positionRange=None, rangeShrink=None):
    viewName = viewName if viewName else "Red"
    rows = rows if rows else 4
    columns = columns if columns else 6

    sliceWidget = slicer.app.layoutManager().sliceWidget(viewName)

    if positionRange is None:
      sliceBounds = [0,0,0,0,0,0]
      sliceWidget.sliceLogic().GetLowestVolumeSliceBounds(sliceBounds)
      slicePositionRange = [sliceBounds[4], sliceBounds[5]]
    else:
      slicePositionRange = [positionRange[0], positionRange[1]]

    if rangeShrink:
      slicePositionRange[0] += rangeShrink[0]
      slicePositionRange[1] -= rangeShrink[1]

    # Capture red slice view, 30 images, from position -125.0 to 75.0
    # into current folder, with name image_00001.png, image_00002.png, ...
    import ScreenCapture
    screenCaptureLogic = ScreenCapture.ScreenCaptureLogic()
    destinationFolder = 'outputs/Capture-SliceSweep'
    numberOfFrames = rows*columns
    filenamePattern = "_lightbox_tmp_image_%05d.png"
    viewNode = sliceWidget.mrmlSliceNode()
    # Suppress log messages
    def noLog(msg):
        pass
    screenCaptureLogic.addLog=noLog
    # Capture images
    screenCaptureLogic.captureSliceSweep(viewNode, slicePositionRange[0], slicePositionRange[1],
                                         numberOfFrames, destinationFolder, filenamePattern)
    # Create lightbox image
    resultImageFilename = filename if filename else filenamePattern % numberOfFrames
    screenCaptureLogic.createLightboxImage(columns, destinationFolder, filenamePattern, numberOfFrames, resultImageFilename)

    # Save result
    with open(destinationFolder+"/"+resultImageFilename, "rb") as file:
      self.dataValue = file.read()
      self.dataType = "image/png"
      # This could be used to create an image widget: img = Image(value=image, format='png')

    # Clean up
    screenCaptureLogic.deleteTemporaryFiles(destinationFolder, filenamePattern, numberOfFrames if filename else numberOfFrames+1)

  def _repr_mimebundle_(self, include=None, exclude=None):
    import base64
    return { self.dataType: base64.b64encode(self.dataValue).decode() }

class MatplotlibDisplay(object):
  """Display matplotlib plot in a notebook cell.

  This helper function will probably not needed after this issue is fixed:
  https://github.com/jupyter-xeus/xeus-python/issues/224

  Important: set matplotlib to use agg backend::

      import matplotlib
      matplotlib.use('agg')

  Example usage::

      import matplotlib
      matplotlib.use('agg')

      import matplotlib.pyplot as plt
      import numpy as np
      # Data for plotting
      t = np.arange(0.0, 2.0, 0.01)
      s = 1 + np.sin(2 * np.pi * t)
      # Setup plot
      fig, ax = plt.subplots()
      ax.plot(t, s)
      ax.set(xlabel='time (s)', ylabel='voltage (mV)',
            title='About as simple as it gets, folks')
      ax.grid()

      slicernb.displayMatplotlib(plt)

  """
  def __init__(self, fig):
    filename = "__matplotlib_temp.png"
    fig.savefig(filename)
    with open(filename, "rb") as file:
      self.dataValue = file.read()
      self.dataType = "image/png"
    import os
    os.remove(filename)

  def _repr_mimebundle_(self, include=None, exclude=None):
    import base64
    return { self.dataType: base64.b64encode(self.dataValue).decode() }

# Utility functions for customizing what is shown in views

def showVolumeRendering(volumeNode, show=True, presetName=None):
  """Display volume node in 3D views using volume rendering.
  :param volumeNode: volume node to show/hide.
  :param show: set to True to show the volume, False to hide it.
  :param presetName: volume rendering preset name, such as `CT-AAA`, `CT-AAA2`, `CT-Bone`, `CT-Bones`,
    `CT-Cardiac`, `CT-Cardiac2`, `CT-Cardiac3`, `CT-Chest-Contrast-Enhanced`, `CT-Chest-Vessels`,
    `CT-Coronary-Arteries`, `CT-Coronary-Arteries-2`, `CT-Coronary-Arteries-3`,
    `CT-Cropped-Volume-Bone`, `CT-Fat`, `CT-Liver-Vasculature`, `CT-Lung`, `CT-MIP`,
    `CT-Muscle`, `CT-Pulmonary-Arteries`, `CT-Soft-Tissue`, `CT-Air`, `CT-X-ray`,
    `MR-Angio`, `MR-Default`, `MR-MIP`, `MR-T2-Brain`, `DTI-FA-Brain`, `US-Fetal`.

  To get all the volume rendering preset names::

    presets = slicer.modules.volumerendering.logic().GetPresetsScene().GetNodesByClass("vtkMRMLVolumePropertyNode")
    presets.UnRegister(None)
    for presetIndex in range(presets.GetNumberOfItems()):
        print(presets.GetItemAsObject(presetIndex).GetName())

  """
  volRenLogic = slicer.modules.volumerendering.logic()
  if show:
    displayNode = volRenLogic.GetFirstVolumeRenderingDisplayNode(volumeNode)
    if not displayNode:
      displayNode = volRenLogic.CreateDefaultVolumeRenderingNodes(volumeNode)
    displayNode.SetVisibility(True)
    scalarRange = volumeNode.GetImageData().GetScalarRange()
    if not presetName:
      if scalarRange[1]-scalarRange[0] < 1500:
        # small dynamic range, probably MRI
        presetName = 'MR-Default'
      else:
        # larger dynamic range, probably CT
        presetName = 'CT-Chest-Contrast-Enhanced'
    displayNode.GetVolumePropertyNode().Copy(volRenLogic.GetPresetByName(presetName))
  else:
    # hide
    volRenLogic = slicer.modules.volumerendering.logic()
    displayNode = volRenLogic.GetFirstVolumeRenderingDisplayNode(volumeNode)
    if displayNode:
      displayNode.SetVisibility(False)

def reset3DView(viewID=0):
  """Centers the selected 3D view on the currently displayed content.
  :param viewID: integer index of the 3D view node. Valid values are between 0 and `slicer.app.layoutManager().threeDViewCount-1`.
  """
  threeDWidget = slicer.app.layoutManager().threeDWidget(viewID)
  threeDView = threeDWidget.threeDView()
  threeDView.resetFocalPoint()

def setViewLayout(layoutName):
  """Set view arrangement, wchich specifies what kind of views are rendered, and their location and sizes.

  :param layoutName: String that specifies the layout name. Most commonly used layouts are:
        `FourUp`, `Conventional`, `OneUp3D`, `OneUpRedSlice`, `OneUpYellowSlice`,
    `OneUpPlot`, `OneUpGreenSlice`, `Dual3D`, `FourOverFour`, `DicomBrowser`.

  Get full list of layout names::

    for att in dir(slicer.vtkMRMLLayoutNode):
      if att.startswith("SlicerLayout"):
        print(att[12:-4])

  """
  layoutId = eval("slicer.vtkMRMLLayoutNode.SlicerLayout"+layoutName+"View")
  slicer.app.layoutManager().setLayout(layoutId)

def showSliceViewAnnotations(show):
    """Show/hide corner annotations (node name, patient name, etc.) in all slice views.
    """
    # Disable slice annotations immediately
    slicer.modules.DataProbeInstance.infoWidget.sliceAnnotations.sliceViewAnnotationsEnabled=show
    slicer.modules.DataProbeInstance.infoWidget.sliceAnnotations.updateSliceViewFromGUI()
    # Disable slice annotations persistently (after Slicer restarts)
    settings = qt.QSettings()
    settings.setValue('DataProbe/sliceViewAnnotations.enabled', 1 if show else 0)
